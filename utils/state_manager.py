import sqlite3
import datetime
from datetime import timezone

class StateManager:
    def __init__(self, db_path="state.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS network_state (
                    id INTEGER PRIMARY KEY,
                    aae1_link TEXT DEFAULT 'up',
                    smw5_link TEXT DEFAULT 'up',
                    dual_down_since TEXT,        -- 紀錄雙斷開始時間
                    aae1_stable_since TEXT,      -- AAE1 恢復時間
                    smw5_stable_since TEXT,      -- SMW5 恢復時間
                    fabric_active INTEGER DEFAULT 0,
                    fabric_uuid TEXT,
                    current_bw_index INTEGER DEFAULT 0, -- 0:2G, 1:5G, 2:10G
                    last_check_time TEXT
                )
            ''')
            if conn.execute('SELECT COUNT(*) FROM network_state').fetchone()[0] == 0:
                conn.execute('INSERT INTO network_state (id) VALUES (1)')
            conn.commit()
    
    def get_state(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return dict(conn.execute('SELECT * FROM network_state WHERE id = 1').fetchone())

    def update_state(self, **kwargs):
        kwargs['last_check_time'] = datetime.datetime.now(timezone.utc).isoformat()
        columns = ', '.join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE network_state SET {columns} WHERE id = 1", values)
            conn.commit()