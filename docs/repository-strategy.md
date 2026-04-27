# Repository Strategy

Arkashri currently uses two GitHub repositories:

- `KumarAditya1729/Arkashri`: backend, infrastructure, CI, and a gitlink pointer to the frontend.
- `KumarAditya1729/arkashri-frontend`: production Next.js frontend.

The production frontend source of truth is the separate `arkashri-frontend` repository. Root-level Next.js files in `Arkashri` are legacy/compatibility artifacts and must not be treated as the primary production UI unless the team explicitly migrates to a monorepo.

CI in `Arkashri` checks out the frontend repository into `frontend/` explicitly instead of relying on submodule metadata. This avoids failures from stale or missing `.gitmodules` mappings while preserving the two-repository deployment model.

If the team later chooses a monorepo, migrate the frontend source into `Arkashri/frontend`, remove the external gitlink, delete duplicate root frontend artifacts, and update CI to use only files committed in the monorepo.
