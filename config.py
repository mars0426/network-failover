# 頻寬設定 (Mbps)
BW_TIERS = [50, 1000, 2000]
# 流量門檻 (70%)
TRAFFIC_THRESHOLD_PERCENT = 0.7
# 檢查流量的時間區間 (分鐘)
TRAFFIC_CHECK_WINDOW_MINS = 60

# 時間門檻 (分鐘)
FAILOVER_DELAY_MINS = 5     # 雙斷後持續多久才啟動 Fabric
RECOVERY_DELAY_MINS = 5     # 恢復後持續多久才關閉 Fabric

# 檢查週期 (秒)
CHECK_INTERVAL_SECONDS = 60

# Gmail 設定
GMAIL_USER = ""
GMAIL_APP_PASSWORD = ""

# Equinix 設定
EQUINIX_CLIENT_ID = ""
EQUINIX_CLIENT_SECRET = ""
ASIDE_PORT_UUID = ""
ZSIDE_PORT_UUID = ""

# Juniper 設定
JUNIPER_HOST = ""
JUNIPER_USER = ""
JUNIPER_PASSWORD = ""
AAE1_PORT_NAME = ""
SMW5_PORT_NAME = ""
USE_JUNIPER_API = False