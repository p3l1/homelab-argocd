# Apps

Jede Anwendung liegt vollständig in diesem Repository — es gibt keine
separaten Repos mehr.

```
apps/<name>/
├── base/
│   ├── application.yaml   ArgoCD-Application: Upstream-Chart und/oder config/
│   └── kustomization.yaml
├── config/                eigene Manifeste (Namespace, Datenbank, Deployment …)
└── overlays/<projekt>/
    ├── config.json        von den ApplicationSets der Projekte eingelesen
    └── kustomization.yaml
```

`<projekt>` ist `infrastructure` oder `apps`; die zugehörigen ApplicationSets
stehen unter `projects/`.

## Infrastructure

| App | Chart | Zweck |
|---|---|---|
| `metallb` | `0.15.3` | LoadBalancer-Adressen, Pool `10.35.99.230–250` |
| `cert-manager` | `v1.21.1` | Zertifikate, cluster-lokale CA |
| `longhorn` | `1.12.1` | verteilter Speicher über die Node-SSDs |
| `cloudnative-pg` | `0.29.0` | PostgreSQL-Operator |
| `newt` | `1.5.0` | Pangolin-Tunnel nach außen |

Die Reihenfolge steuern Sync-Waves: MetalLB zuerst, danach cert-manager,
Longhorn, CloudNativePG und zuletzt Newt.

## Apps

| App | Quelle | Zweck |
|---|---|---|
| `whoami` | eigene Manifeste | Testdienst für Ingress und DNS |
| `umami` | Chart `7.11.5` | Web-Analyse, Datenbank über CloudNativePG |
| `paperless-ngx` | Chart `0.24.1` | Dokumentenverwaltung |
| `tekton-pipelines` | Chart `1.14.0` | CI |
| `arcane` | eigene Manifeste | Verwaltung der externen Docker-Hosts |

Secrets liegen SOPS-verschlüsselt unter [`secrets/`](../secrets) und werden
von Hand angewandt, nicht von ArgoCD.
