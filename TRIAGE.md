# Triage

> Phase 0 triage notes for the nine capstone defects.

## 1. `scripts/ingest.sh` is not executable
**Symptom:** The verifier checks that `scripts/ingest.sh` has executable permission.

**Cause:** The script must have the executable Git file mode so it can be run directly with `./scripts/ingest.sh`.

**Fix:** The script is tracked with executable mode `100755`.

**Proof:** `./scripts/verify.sh` reports `PASS  ingest.sh is executable`.

**Why `git update-index --chmod=+x` was also needed:** File permissions are tracked by Git, so changing the local permission alone is not enough to record the executable bit in the repository.

## 2. Unquoted `$1` in `scripts/ingest.sh`
**Symptom:** An unquoted command-line argument can be split when the supplied file path contains spaces.

**Cause:** Shell variables are subject to word splitting when they are not quoted.

**Fix:** The script uses `"$1"` wherever the input file path is used.

**Proof:** `./scripts/verify.sh` reports `PASS  $1 is quoted in ingest.sh`.

## 3. Dockerfile copies source before installing dependencies
**Symptom:** The Dockerfile copied the entire source tree before installing Python dependencies.

**Cause:** Any source-code change could invalidate the Docker build cache before the dependency installation layer.

**Fix:** The Dockerfile now copies `api/requirements.txt`, installs dependencies, and only then runs `COPY . .`.

**Proof (build order):** The Dockerfile now has `COPY api/requirements.txt` followed by `RUN pip install --no-cache-dir -r api/requirements.txt`, followed by `COPY . .`.

## 4. No `.dockerignore`
**Symptom:** Docker had no ignore file, so unnecessary repository files could be included in the build context.

**Cause:** A `.dockerignore` file had not been created.

**Fix:** Created `.dockerignore` excluding `.git`, `.terraform/`, `__pycache__/`, `*.pyc`, and `.venv/`.

**Proof (context exclusions):** `cat .dockerignore` shows the required exclusions.

## 5. API key committed to the repository
**Symptom:** A hardcoded API key was present in `api/config.py` and `.github/workflows/ci.yml`.

**Cause:** Credentials had been written directly into source and workflow configuration.

**Fix:** `api/config.py` now reads `API_KEY` from the environment, and the CI workflow reads it from `${{ secrets.API_KEY }}`.

**Is the key gone now that you deleted the line?** The key is gone from the current source files, but it remains in Git history.

**What would you have to do in real life?** Immediately revoke or rotate the exposed credential, replace it with a new secret, store it in a proper secret manager, and remove the exposed credential from Git history when appropriate.

## 6. `requests` call with no timeout
**Symptom:** `requests.get()` could wait indefinitely if the remote server accepted the connection but stopped responding.

**Cause:** No timeout value was supplied to the HTTP request.

**Fix:** Added `timeout=10` to `requests.get(url)`.

**Why a hang is worse than an error:** A timeout allows the application to fail predictably and recover, while an indefinite hang can consume resources and block processing.

## 7. Missing index on `orders.customer_id`
**Symptom:** Queries filtering or joining on `orders.customer_id` could require a sequential scan when no suitable index exists.

**Plan before:** The expected baseline plan is a sequential scan on the orders table.

**Plan after:** After creating the customer ID index, the planner can use an index scan when the query and table statistics make it beneficial.

**Timings, three runs each:** EXPLAIN ANALYZE evidence will be captured during the query phase before and after the index is applied.

**Why the planner changed its mind:** The index gives PostgreSQL a faster access path to rows matching `customer_id`; the optimizer chooses it when its cost estimate is lower than scanning the whole table.

## 8. SSH open to `0.0.0.0/0`
**Symptom:** Security group ingress allowed TCP port 22 from every IPv4 address.

**Why nothing warned you:** Infrastructure-as-code can successfully validate syntactically while still containing an insecure network rule unless security policies or scanners detect it.

**Fix:** Restricted SSH ingress from `0.0.0.0/0` to `10.0.0.0/16`.

**What an attacker does with this:** An internet-exposed SSH service can be discovered and targeted with scanning, password attacks, credential attacks, or exploitation of vulnerabilities.

## 9. `count` instead of `for_each`
**Plan with `count`, after removing `staging`:** With `count`, removing the middle `staging` element shifts later list indexes, so Terraform can plan changes to the wrong resource addresses.

**Plan with `for_each`, same edit:** With `for_each`, resources are addressed by stable environment keys such as `dev` and `prod`, so removing `staging` does not shift the remaining resources.

**Why this is the most dangerous defect in the list:** Incorrect resource addressing can cause Terraform to destroy and recreate infrastructure unexpectedly, potentially causing outages or data loss.
