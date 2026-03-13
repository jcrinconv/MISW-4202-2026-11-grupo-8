from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("auth_anomaly.app:app", host="0.0.0.0", port=6005, reload=False)
