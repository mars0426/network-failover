import requests
import json
import logging

class EquinixClient:
    def __init__(self, client_id, client_secret, is_sandbox=False):
        self.base_url = "https://sandbox.api.equinix.com" if is_sandbox else "https://api.equinix.com"
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = self._get_token()
    
    def _get_token(self):
        # 取得 OAuth2 Access Token
        url = f"{self.base_url}/oauth2/v1/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        response = requests.post(url, data=payload)
        response.raise_for_status()
        return response.json()['access_token']
    
    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def get_connection_stats(self, connection_uuid, start_time_iso, end_time_iso):
        # 取得連線的流量統計數據
        url = f"{self.base_url}/fabric/v4/connections/{connection_uuid}/stats"
        params = {
            "startDateTime": start_time_iso,
            "endDateTime": end_time_iso,
            "viewPoint": "aSide"
        }
        
        response = requests.get(url, params=params, headers=self.get_headers())
        if response.status_code == 200:
            return response.json().get('stats', []).get('bandwidthUtilization', [])
        else:
            print(f"Failed to get stats: {response.text}")
            return []
       
    def update_bandwidth(self, connection_uuid, bandwidth_mbps):
        # 調整頻寬
        url = f"{self.base_url}/fabric/v4/connections/{connection_uuid}"
        payload = [
            {
                "op": "replace",
                "path": "/bandwidth",
                "value": bandwidth_mbps
            }
        ]

        headers = self.get_headers()
        headers["Content-Type"] = "application/json-patch+json"
        response = requests.patch(url, json=payload, headers=headers)
        if response.status_code in [200, 202]:
            print(f"Successfully requested bandwidth update to {bandwidth_mbps}Mbps")
            return True
        else:
            print(f"Update failed: {response.text}")
            return False
    
    def create_port_to_port_connection(self, name, a_side_port_uuid, z_side_port_uuid, bandwidth_mbps):
        # 建立連線 (從一個實體 Port 到另一個實體 Port)
        url = f"{self.base_url}/fabric/v4/connections"
        payload = {
            "name": name,
            "type": "EVPL_VC",  # 乙太虛擬專線
            "bandwidth": bandwidth_mbps,
            "notifications": [
                {
                    "type": "ALL",  # 通知類型，通常設為 ALL (包含佈署、變更、故障等)
                    "emails": ["ch@cht.com.tw"]  # 修改為您或維運團隊的 Email
                }
            ],
            "redundancy": {"priority": "PRIMARY"},
            "aSide": {
                "accessPoint": {
                    "type": "COLO",
                    "port": {"uuid": a_side_port_uuid},
                    "linkProtocol": {"type": "DOT1Q", "vlanTag": 101} # 你的 VLAN ID
                }
            },
            "zSide": {
                "accessPoint": {
                    "type": "COLO",
                    "port": {"uuid": z_side_port_uuid},
                    "linkProtocol": {"type": "DOT1Q", "vlanTag": 101}
                }
            }
        }
        
        response = requests.post(url, json=payload, headers=self.get_headers())
        if response.status_code == 201:
            conn_id = response.json()['uuid']
            print(f"Connection created successfully! ID: {conn_id}")
            return conn_id
        else:
            print(f"Creation failed: {response.text}")
            return None
    
    def delete_connection(self, connection_uuid):
        # 刪除/關閉連線
        url = f"{self.base_url}/fabric/v4/connections/{connection_uuid}"
        response = requests.delete(url, headers=self.get_headers())
        
        if response.status_code in [202, 204]:
            print("Connection deletion requested successfully.")
            return True
        else:
            print(f"Deletion failed: {response.text}")
            return False
