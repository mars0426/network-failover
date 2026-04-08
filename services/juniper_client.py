import logging
from jnpr.junos import Device
from jnpr.junos.exception import ConnectError, ProbeError, ConnectAuthError

class JuniperClient:
    def __init__(self, host, user, pwd):
        self.host = host
        self.user = user
        self.pwd = pwd
        # 定義設備連線參數
        self.dev = Device(host=host, user=user, passwd=pwd, port=22) # 預設使用 NETCONF (SSH Port 22)

    def is_port_up(self, port_name):
        """
        透過 NETCONF/RPC 取得介面狀態
        回傳: True (Up), False (Down), None (連線失敗或找不到 Port)
        """
        try:
            # 1. 建立連線
            self.dev.open()
            
            # 2. 執行 RPC 指令: <get-interface-information><terse/><interface-name>...
            # 相當於 CLI 下的 "show interfaces terse <port_name>"
            res = self.dev.rpc.get_interface_information(interface_name=port_name, terse=True)
            
            # 3. 解析 XML 結果
            # 尋找 <oper-status> 節點
            # 注意：Juniper 的 XML 結構中，狀態位在 physical-interface 或 logical-interface 下
            oper_status = res.xpath(f".//interface-name[contains(text(), '{port_name}')]/../oper-status")
            
            if oper_status:
                status_text = oper_status[0].text.strip().lower()
                logging.info(f"[Juniper] Port {port_name} 狀態偵測結果: {status_text}")
                return status_text == "up"
            else:
                logging.warning(f"[Juniper] 找不到介面 {port_name} 的狀態資訊")
                return None

        except ConnectAuthError:
            logging.error(f"[Juniper] 認證失敗: 請檢查帳號密碼。")
            return None
        except ConnectError as e:
            logging.error(f"[Juniper] 無法連線至設備 {self.host}: {e}")
            return None
        except Exception as e:
            logging.error(f"[Juniper] 偵測程序發生非預期錯誤: {e}")
            return None
        finally:
            # 4. 確保關閉連線
            if self.dev.connected:
                self.dev.close()
