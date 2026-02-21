# Cloud Deployment Roadmap (Provider-Agnostic)

## Phase 0: Local MVP
- Single-machine Docker Compose deployment.
- Local volumes for job artifacts.
- Local LLM runtime.

## Phase 1: Lift-and-Shift Containers
- Push images to cloud container registry.
- Deploy unchanged containers to a managed container runtime.
- Keep queue and storage managed in cloud.

## Phase 2: Managed Data Plane
- Move artifacts to object storage.
- Replace local Redis with managed queue/cache.
- Centralize secrets/config with cloud secret manager.

## Phase 3: Production Hardening
- Add auth for upload endpoints.
- Add rate limiting and request validation.
- Add observability (structured logs, traces, metrics).
- Add lifecycle policies for artifact retention.

## Phase 4: Performance and Cost
- Introduce autoscaling workers by queue depth.
- Separate GPU and CPU worker pools.
- Route short and long jobs to different queues.

## Reference Cloud Service Mapping
- Compute: Kubernetes, serverless containers, or VM-based container hosts.
- Queue: Redis-compatible queue or managed message bus.
- Storage: object store for raw and processed artifacts.
- Secrets: cloud secret manager.
- Monitoring: cloud logging + metrics + traces.
