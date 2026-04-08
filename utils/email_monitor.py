import imaplib
import email
from email.header import decode_header

class EmailMonitor:
    def __init__(self, user, password):
        self.user = user
        self.password = password
        self.imap_url = 'imap.gmail.com'

    def fetch_latest_alerts(self):
        """
        搜尋未讀郵件，並僅根據「主旨」解析海纜狀態。
        回傳格式: [{'cable': 'SMW5', 'status': 'up'}, ...]
        """
        alerts = []
        try:
            # 1. 登入 Gmail
            mail = imaplib.IMAP4_SSL(self.imap_url)
            mail.login(self.user, self.password)
            mail.select("inbox")

            # 2. 搜尋所有未讀 (UNSEEN) 郵件
            status, messages = mail.search(None, 'UNSEEN')
            if status != 'OK' or not messages[0]:
                return alerts

            # 3. 逐一處理郵件
            for num in messages[0].split():
                # 僅抓取郵件標頭 (Header)，不抓取內文以節省資源
                res, msg_data = mail.fetch(num, '(BODY[HEADER.FIELDS (SUBJECT)])')
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # 4. 解碼主旨 (處理可能的 UTF-8 或 Base64 編碼)
                        raw_subject = msg["Subject"]
                        if raw_subject:
                            subject_parts = decode_header(raw_subject)
                            subject_text = ""
                            for content, encoding in subject_parts:
                                if isinstance(content, bytes):
                                    subject_text += content.decode(encoding if encoding else "utf-8")
                                else:
                                    subject_text += str(content)
                            
                            # 5. 根據主旨內容判定狀態 (轉大寫比對避免誤差)
                            alert = self._parse_subject(subject_text.upper())
                            if alert:
                                alerts.append(alert)
                                print(f"[Email Monitor] 解析成功: {subject_text}")

            mail.logout()
        except Exception as e:
            print(f"[Email Monitor] 發生錯誤: {e}")
            
        return alerts

    def _parse_subject(self, subject):
        """
        邏輯判斷：主旨必須同時包含 [海纜名] 與 [狀態字]
        """
        # 定義要檢查的海纜與狀態
        cables = ["SMW5", "AAE1"]
        
        for cable in cables:
            if cable in subject:
                if "LINK UP" in subject:
                    return {"cable": cable, "status": "up"}
                elif "LINK DOWN" in subject:
                    return {"cable": cable, "status": "down"}
        
        return None
