import sys
import io
import time
import datetime
import logging
from datetime import timezone
from config import *
from utils.state_manager import StateManager
from utils.email_monitor import EmailMonitor
from services.equinix_client import EquinixClient
from services.juniper_client import JuniperClient

# 標準輸出使用 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置 Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        # 檔案端：指定 utf-8
        logging.FileHandler("app.log", encoding='utf-8'), 
        # 螢幕端：指定使用前面處理過的 sys.stdout
        logging.StreamHandler(sys.stdout) 
    ]
)

def run_orchestrator():
    stateManager = StateManager()
    emailMonitor = EmailMonitor(GMAIL_USER, GMAIL_APP_PASSWORD)
    equinixClient = EquinixClient(EQUINIX_CLIENT_ID, EQUINIX_CLIENT_SECRET)
    juniperClient = JuniperClient(JUNIPER_HOST, JUNIPER_USER, JUNIPER_PASSWORD)
    
    while True:
        try:
            logging.info(f"--- 輪詢開始 (模式: {'Juniper API + Email' if USE_JUNIPER_API else '僅 Email'}) ---")
            state = stateManager.get_state()
            now = datetime.datetime.now(timezone.utc)

            # 1. 取得所有未讀 Email 告警 (不論模式為何都要抓取以清空未讀郵件)
            alerts = emailMonitor.fetch_latest_alerts()

            # 2. 根據 FLAG 判定 Link 狀態
            if USE_JUNIPER_API:
                # A. 透過 API 偵測 Port 狀態 (回傳 True 為 Up, False 為 Down)
                aae1_port_up = juniperClient.is_port_up(AAE1_PORT_NAME)
                smw5_port_up = juniperClient.is_port_up(SMW5_PORT_NAME)

                # 準備更新字典
                new_statuses = {}

                # 處理 AAE1
                is_aae1_mail_up = any(a['cable'].lower() == 'aae1' and a['status'].lower() == 'up' for a in alerts)
                if aae1_port_up is False:
                    new_statuses['aae1'] = 'down'
                if aae1_port_up is True or is_aae1_mail_up:
                    new_statuses['aae1'] = 'up'
                
                # 處理 SMW5
                is_smw5_mail_up = any(a['cable'].lower() == 'smw5' and a['status'].lower() == 'up' for a in alerts)
                if smw5_port_up is False:
                    new_statuses['smw5'] = 'down'
                if smw5_port_up is True or is_smw5_mail_up:
                    new_statuses['smw5'] = 'up'
                
                # 將判定結果寫入資料庫
                for cable, status in new_statuses.items():
                    if state[f"{cable}_link"] != status:
                        update_fields = {f"{cable}_link": status}
                        if status == 'down':
                            update_fields[f"{cable}_stable_since"] = None
                            logging.warning(f"[API/Mail] 偵測到告警: {cable.upper()} Link Down")
                        else:
                            update_fields[f"{cable}_stable_since"] = now.isoformat()
                            logging.info(f"[API/Mail] 偵測到告警: {cable.upper()} Link Up")
                        stateManager.update_state(**update_fields)
            
            else:
                # B. 僅依據 Email 判斷
                for alert in alerts:
                    cable = alert['cable'].lower() # aae1 or smw5
                    status = alert['status'] # up or down
                    
                    # 如果狀態有變動
                    if state[f"{cable}_link"] != status:
                        update_fields = {f"{cable}_link": status}
                        if status == 'down':
                            update_fields[f"{cable}_stable_since"] = None
                            logging.warning(f"[Mail] 偵測到告警: {cable.upper()} Link Down")
                        else:
                            update_fields[f"{cable}_stable_since"] = now.isoformat()
                            logging.info(f"[Mail] 偵測到告警: {cable.upper()} Link Up")
                        stateManager.update_state(**update_fields)
            
            # 重新取得最新狀態
            state = stateManager.get_state()

            # 2. 海纜雙斷邏輯判斷
            if state['aae1_link'] == 'down' and state['smw5_link'] == 'down':
                if not state['dual_down_since']:
                    stateManager.update_state(dual_down_since=now.isoformat())
                    logging.warning("目前處於雙斷狀態，開始計時。")
                else:
                    # 檢查是否超過指定分鐘數且 Fabric 未啟動
                    start_time = datetime.datetime.fromisoformat(state['dual_down_since'])
                    if (now - start_time).total_seconds() >= FAILOVER_DELAY_MINS * 60:
                        if not state['fabric_active']:
                            logging.info(f"雙斷超過 {FAILOVER_DELAY_MINS} 分鐘，啟動 Fabric 連線...")
                            new_uuid = equinixClient.create_port_to_port_connection(
                                "FABRIC_FAILOVER", ASIDE_PORT_UUID, ZSIDE_PORT_UUID, BW_TIERS[0]
                            )
                            if new_uuid:
                                stateManager.update_state(fabric_active=1, fabric_uuid=new_uuid, current_bw_index=0)
                                logging.info(f"Fabric 已建立, UUID: {new_uuid}")
            else:
                # 若任一海纜非 Down，重置雙斷計時
                if state['dual_down_since']:
                    stateManager.update_state(dual_down_since=None)

            # 3. 頻寬動態調整 (Fabric 啟動期間)
            if state['fabric_active'] and state['fabric_uuid']:
                current_idx = state['current_bw_index']
                if current_idx < len(BW_TIERS) - 1: # 若未達最高級
                    current_bw = BW_TIERS[current_idx]
                    # 獲取過去一小時流量
                    ago = now - datetime.timedelta(minutes=TRAFFIC_CHECK_WINDOW_MINS)
                    start_iso = ago.strftime('%Y-%m-%dT%H:%M:%SZ')
                    end_iso = now.strftime('%Y-%m-%dT%H:%M:%SZ')
                    stats = equinixClient.get_connection_stats(state['fabric_uuid'], start_iso, end_iso)
                    if not stats:
                        logging.info("暫無流量數據。")
                    else:
                        inbound = stats.get('inbound', [])
                        outbound = stats.get('outbound', [])
                        mean_traffic_bps = max(inbound["mean"], outbound["mean"])
                        if mean_traffic_bps >= current_bw * TRAFFIC_THRESHOLD_PERCENT:
                            new_idx = current_idx + 1
                            logging.info(f"流量持續超過 {TRAFFIC_THRESHOLD_PERCENT * 100}%，準備升級頻寬至 {BW_TIERS[new_idx]}M")
                            success = equinixClient.update_bandwidth(state['fabric_uuid'], BW_TIERS[new_idx])
                            if success:
                                logging.info("頻寬調升成功。")
                            else:
                                logging.info("頻寬調升失敗。")

            # 4. 海纜恢復邏輯判斷
            if (state['aae1_link'] == 'up' or state['smw5_link'] == 'up') and state['fabric_active']:
                # 找出是哪一條恢復了且穩定
                for cable in ['aae1', 'smw5']:
                    stable_since = state[f"{cable}_stable_since"]
                    if state[f"{cable}_link"] == 'up' and stable_since:
                        start_stable = datetime.datetime.fromisoformat(stable_since)
                        if (now - start_stable).total_seconds() >= RECOVERY_DELAY_MINS * 60:
                            logging.info(f"{cable.upper()} 已穩定超過指定時間，關閉 Fabric 連線。")
                            if equinixClient.delete_connection(state['fabric_uuid']):
                                stateManager.update_state(fabric_active=0, fabric_uuid=None, current_bw_index=0)
                                logging.info("Fabric 連線已成功關閉並清除紀錄。")
                            break # 處理一條即可

        except Exception as e:
            logging.error(f"主邏輯執行發生錯誤: {e}", exc_info=True)

        logging.info(f"等待 {CHECK_INTERVAL_SECONDS} 秒後進行下次檢查...")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    run_orchestrator()
    # 1. 初始化元件
    stateManager = StateManager("state.db") # 持久化紀錄 AAE1/SMW5 狀態
    emailMonitor = EmailMonitor(user=email_username, password=email_password)
    equinixClient = EquinixClient(client_id=equinix_cliend_id, client_secret=equinix_cliend_secret)

    # 2. 從 Gmail 抓取新郵件告警並更新資料庫狀態
    new_alerts = emailMonitor.fetch_latest_alerts()
    for alert in new_alerts:
        # update_link_status 會自動判斷狀態是否有變動，並寫入計時器 (aae1_stable_since 等)
        stateManager.update_link_status(alert['cable'], alert['status'])
        print(f"-> 偵測到 Email 狀態變更: {alert['cable']} 變更為 {alert['status']}")

    # 3. 讀取最新資料庫狀態進行邏輯判斷
    current_state = stateManager.load_state()
    aae1 = current_state['aae1_link']
    smw5 = current_state['smw5_link']
    is_fabric_active = current_state['fabric_active']  # 1 為啟動, 0 為關閉
    
    # --- 邏輯 A: 故障轉移 (Failover) ---
    # 條件：兩條海纜都 Down，且 Fabric 目前尚未啟動
    if aae1 == 'down' and smw5 == 'down':
        if is_fabric_active == 0:
            print("!!! 警報: AAE1 與 SMW5 同時斷線，執行 Fabric 啟動程序 !!!")
            
            # 呼叫 API 建立連線或調升頻寬 (依據開會結論，建議用 update_bandwidth)
            # 這裡以建立連線為例，初始頻寬 2G (2000 Mbps)
            success = equinixClient.create_port_to_port_connection("CHT", a_side_port_uuid, z_side_port_uuid, 2000)
            
            if success:
                stateManager.reset_fabric_status(active=True)
                print("成功: Fabric Connection 已切換至最高優先權 (2G)。")
            else:
                print("失敗: 無法透過 API 啟動 Fabric，請人工介入！")
        else:
            print("狀態: 目前維持於 Fabric 備援連線中。")

    # --- 邏輯 B: 恢復回切 (Revert) ---
    # 條件：任一海纜 Up，且目前正在跑 Fabric，且已穩定運行 8 小時 (480 分鐘)
    elif (aae1 == 'up' or smw5 == 'up') and is_fabric_active == 1:
        # 檢查資料庫中的計時器是否超過 480 分鐘
        if stateManager.check_stability(minutes=480):
            print("--- 訊息: 海纜已穩定運作超過 8 小時，執行回切程序 ---")
            
            # 呼叫 API 關閉或將頻寬調至最低 (例如 10 Mbps)
            success = equinixClient.update_bandwidth(FABRIC_CONN_UUID, 10)
            
            if success:
                stateManager.reset_fabric_status(active=False)
                print("成功: 已切換回海纜，Fabric Connection 權重已調低。")
            else:
                print("失敗: 回切過程 API 呼叫失敗。")
        else:
            # 尚在 8 小時觀察期內
            print("狀態: 海纜已恢復，但尚未通過 8 小時穩定測試。")

    else:
        print(f"狀態正常: AAE1={aae1}, SMW5={smw5}, Fabric_Active={is_fabric_active}")

    print(f"[{datetime.datetime.now()}] 監測任務完成。\n")