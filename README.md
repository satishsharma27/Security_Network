### Network Security Project For Phising Data

Project structure
Pipeline Flow

MongoDB Database
      │
      ▼
Data Ingestion Component  ◄── Data Ingestion Config   ──► Data Ingestion Artifacts
      │
      ▼
Data Validation Component ◄── Data Validation Config   ──► Data Validation Artifacts
      │
      ▼
Data Transformation Comp. ◄── Data Transformation Config ──► Data Transformation Artifacts
      │
      ▼
Model Trainer Component   ◄── Model Trainer Config     ──► Model Trainer Artifacts
      │
      ▼
Model Evaluation Comp.    ◄── Model Evaluation Config  ──► Model Evaluation Artifacts
      │
      ├── Model Accepted? Yes ──► Model Pusher Component ◄── Model Pusher Config ──► Model Pusher Artifacts
      │
      └── No ──► None

