"""FastAPI server exposing detections and follower data.

Routes planned for v0.1:
    GET  /api/detections       — paginated raw detections
    GET  /api/followers        — current follower list
    GET  /api/followers/{id}/track — geo trace for one follower
    GET  /                     — serves the Leaflet web UI
    WS   /ws/live              — live updates (optional)
"""