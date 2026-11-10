"""Small extension to the existing trade ledger; old trades are untouched."""
V20_STATEMENTS=(
'''CREATE TABLE ai_trade_checks(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 absolute_day INTEGER NOT NULL,agency_id TEXT NOT NULL REFERENCES agencies(id),PRIMARY KEY(game_id,absolute_day,agency_id))''',
'''CREATE TABLE ai_trade_windows(trade_id TEXT PRIMARY KEY REFERENCES market_trades(id) ON DELETE CASCADE,
 deadline_day INTEGER NOT NULL,counter_count INTEGER NOT NULL DEFAULT 0 CHECK(counter_count BETWEEN 0 AND 3),
 revision INTEGER NOT NULL DEFAULT 1,counter_history_json TEXT NOT NULL DEFAULT '[]',read_seq INTEGER NOT NULL DEFAULT 0)''',
'''CREATE TABLE ai_trade_messages(id INTEGER PRIMARY KEY,trade_id TEXT NOT NULL REFERENCES ai_trade_windows(trade_id) ON DELETE CASCADE,
 absolute_day INTEGER NOT NULL,sender TEXT NOT NULL,message TEXT NOT NULL)''',
"CREATE INDEX ai_trade_messages_by_trade ON ai_trade_messages(trade_id,id)",
)
