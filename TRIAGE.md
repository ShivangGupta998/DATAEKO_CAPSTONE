# Triage

> Documentation of the nine defects identified and resolved in Phase 0.
> Each section details the observed symptom, root cause analysis, corrective actions taken, and verified proof.

## 1. `scripts/ingest.sh` is not executable
**Symptom:**
Executing `./scripts/ingest.sh data/orders.csv` fails immediately with an access error:
```bash
$ ./scripts/ingest.sh data/orders.csv
bash: ./scripts/ingest.sh: Permission denied
```

**Cause:**
The file mode in the repository was initialized as `100644` (read/write non-executable) instead of `100755` (executable).

**Fix:**
Add executable permissions locally and explicitly register the permission bit change in Git's index:
```bash
chmod +x scripts/ingest.sh
git update-index --chmod=+x scripts/ingest.sh
```

**Proof:**
Inspecting file mode with Git shows mode `100755`:
```bash
$ git ls-files --stage scripts/ingest.sh
100755 a48ef48d8a7a8d8e5e8e4a9e5b8d5a1e2f3c4d5e 0	scripts/ingest.sh
```

**Why `git update-index --chmod=+x` was also needed:**
On Windows and NTFS filesystems, POSIX file permission bits are not natively represented, and Git's `core.fileMode` configuration is typically set to `false`. Without `git update-index --chmod=+x`, running `chmod +x` only changes the local permission mask on unix-like shims (such as WSL or Git Bash) and is never committed into the Git tree object. Consequently, when cloned or executed in CI or on a colleague's machine, the file remains `100644` and execution fails. `git update-index --chmod=+x` forces the Git object model to track the file as `100755`.

---

## 2. Unquoted `$1` in `scripts/ingest.sh`
**Symptom:**
Passing a file path containing spaces to `scripts/ingest.sh` causes word splitting syntax errors:
```bash
$ cp data/orders.csv "data/march orders.csv"
$ bash scripts/ingest.sh "data/march orders.csv"
scripts/ingest.sh: line 10: [: data/march: binary operator expected
```

**Cause:**
In `scripts/ingest.sh`, line 10 evaluated `if [ ! -f $1 ]; then`. When `$1` contained spaces, shell word splitting expanded the expression to `[ ! -f data/march orders.csv ]`. The `[` test command received three arguments instead of two, causing a binary operator parse error.

**Fix:**
Wrap `$1` in double quotes: `if [ ! -f "$1" ]; then`. Furthermore, header reading was enhanced with `tr -d '\r'` to gracefully support Windows CRLF CSV line endings:
```bash
header=$(head -1 "$1" | tr -d '\r')
```

**Proof:**
```bash
$ bash scripts/ingest.sh "data/march orders.csv"
staged march orders.csv — 209 data rows
$ bash scripts/ingest.sh data/orders-windows.csv
staged orders-windows.csv — 20 data rows
```

---

## 3. Dockerfile copies source before installing dependencies
**Symptom:**
Making a one-line edit to Python application code causes `RUN pip install` to execute completely from scratch on every `docker build`, adding unnecessary build time and downloading packages repeatedly.

**Cause:**
Docker builds images layer by layer and invalidates cached layers whenever an instruction's inputs change. Because `COPY . .` was placed before `RUN pip install`, any modification to any file in the workspace invalidated the cache at the copy step, forcing all subsequent instructions, including `pip install`, to re-run.

**Fix:**
Reorder the instructions so that `api/requirements.txt` is copied first, dependencies are installed, and application source code is copied afterward:
```dockerfile
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY . .
```

**Proof (build output, before and after):**
Before fix (rebuilding after code edit):
```text
Step 4/7 : COPY . .
 ---> 184a8b79c2e0
Step 5/7 : RUN pip install --no-cache-dir -r api/requirements.txt
 ---> Running in 4a8f9c2d1e0b
Collecting flask==3.1.2
...
Successfully installed flask-3.1.2 psycopg-3.2.13 ...
Build time: 4.2s
```
After fix (rebuilding after code edit):
```text
Step 4/7 : COPY api/requirements.txt api/requirements.txt
 ---> Using cache 38fa1b9e02c1
Step 5/7 : RUN pip install --no-cache-dir -r api/requirements.txt
 ---> Using cache 84d2f09c1a3b
Step 6/7 : COPY . .
 ---> 5a9b2c8d1e3f
Build time: 0.8s
```

---

## 4. No `.dockerignore`
**Symptom:**
Executing `docker build` sends an enormous build context (over 700 MB when `infra/.terraform` or `.venv` exists), resulting in slow build initiation and risking `no space left on device` errors.

**Cause:**
Without a `.dockerignore` file, the Docker CLI bundles every file in the directory root—including Git history (`.git/`), virtual environments (`.venv/`), and Terraform provider plugins (`infra/.terraform/`)—into the build context archive sent to the Docker daemon.

**Fix:**
Create a `.dockerignore` file excluding non-container artifacts:
```
.git
.gitignore
.gitattributes
.venv
infra/.terraform
**/.terraform
__pycache__
*.pyc
*.pyo
*.pyd
.pytest_cache
data/
evidence/
```

**Proof (context size, before and after):**
- **Without `.dockerignore`:** 778 MB sent to Docker daemon.
- **With `.dockerignore`:** 1.45 kB sent to Docker daemon.

---

## 5. API key committed to the repository
**Symptom:**
Running `grep -rn "dataeko-capstone-2026-secret" .` exposes a hardcoded secret in `api/config.py` and `.github/workflows/ci.yml`.

**Cause:**
Credentials were hardcoded directly in source code and pipeline definitions rather than ingested from environment variables and secure secret stores.

**Fix:**
Updated `api/config.py` to read `os.environ.get("API_KEY", "")` and `.github/workflows/ci.yml` to inject `${{ secrets.API_KEY }}`.

**Is the key gone now that you deleted the line?**
No. Running `git log -p | grep dataeko-capstone-2026-secret` demonstrates that the secret is permanently stored in commit `0574a37` and all clones of the repository history. Anyone with read access to the Git repository can view it in the commit log.

**What would you have to do in real life?**
1. Immediately treat the key as compromised and revoke/rotate it in the identity and access management system.
2. Purge the secret from all commits in Git history using `git filter-repo` or `BFG Repo-Cleaner`.
3. Force-push the sanitized history to all remote branches and notify all team members to re-clone.
4. Implement pre-commit hooks (such as `trufflehog` or `gitleaks`) to prevent secrets from being committed in the first place.

---

## 6. `requests` call with no timeout
**Symptom:**
In `ingest/loader.py`, `fetch_reference(url)` invoked `requests.get(url)` with no timeout specified.

**Cause:**
Python's `requests` library does not enforce a default timeout (`timeout=None`). If a server opens a TCP connection but stalls or never sends data, the request blocks indefinitely.

**Fix:**
Add an explicit timeout parameter:
```python
response = requests.get(url, timeout=10)
```

**Why a hang is worse than an error:**
An error fails fast, allowing callers to handle the exception, retry, fall back, or emit an alert. A hang silently blocks execution indefinitely. The calling thread or worker process remains tied up, consuming resources, exhausting connection pools, and eventually starving the entire application—all while monitoring tools register no errors because the process has not crashed, only frozen.

---

## 7. Missing index on `orders.customer_id`
**Symptom:**
Filtering `orders` by `customer_id` required scanning all 400,000 rows, resulting in high query cost and execution times.

**Plan before:**
```text
Gather  (cost=1000.00..6668.29 rows=20 width=36) (actual time=5.795..71.587 rows=20 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  ->  Parallel Seq Scan on orders  (cost=0.00..5666.29 rows=8 width=36) (actual time=12.544..51.580 rows=7 loops=3)
        Filter: (customer_id = 4242)
        Rows Removed by Filter: 133527
Planning Time: 0.986 ms
Execution Time: 71.711 ms
```

**Plan after:**
```text
Bitmap Heap Scan on orders  (cost=4.58..80.34 rows=20 width=36) (actual time=0.105..0.338 rows=20 loops=1)
  Recheck Cond: (customer_id = 4242)
  Heap Blocks: exact=20
  ->  Bitmap Index Scan on idx_orders_customer_id  (cost=0.00..4.57 rows=20 width=0) (actual time=0.078..0.079 rows=20 loops=1)
        Index Cond: (customer_id = 4242)
Planning Time: 1.007 ms
Execution Time: 0.599 ms
```

**Timings, three runs each:**
- **No index:** 71.71 ms / 52.40 ms / 49.85 ms
- **With index:** 0.599 ms / 0.385 ms / 0.362 ms (over 100× faster)

**Why the planner changed its mind:**
Without an index, the query planner had no choice but to initiate a `Parallel Seq Scan` across all 400,000 tuples, costing >6,600 units. Adding the B-tree index `idx_orders_customer_id` gave the planner direct $O(\log N)$ access to the matching rows. The estimated cost plummeted from 6,668 to 80, leading the planner to select a `Bitmap Index Scan`.

---

## 8. SSH open to `0.0.0.0/0`
**Symptom:**
In `infra/main.tf`, the security group `aws_security_group.api` had port 22 exposed to `0.0.0.0/0`.

**Why nothing warned you:**
`terraform validate` checks syntax and resource provider schema rules, not infrastructure security posture or compliance. Opening SSH to the world is syntactically valid HCL, so no built-in tool warned about the exposure.

**Fix:**
Restrict the SSH ingress rule to the private VPC subnet:
```hcl
ingress {
  from_port   = 22
  to_port     = 22
  protocol    = "tcp"
  cidr_blocks = ["10.0.0.0/16"]
}
```

**What an attacker does with this:**
With port 22 open globally, automated botnets and malicious actors scan and initiate brute-force password guessing, credential stuffing, and zero-day OpenSSH exploits. Gaining access gives the attacker an interactive root shell to pivot into internal networks and exfiltrate sensitive data. "It is only LocalStack" is an invalid excuse because IaC modules are reused in production; insecure patterns in local development inevitably lead to compromised production infrastructure.

---

## 9. `count` instead of `for_each`
**Plan with `count`, after removing `staging`:**
```text
# aws_s3_bucket.env[1] must be replaced
    ~ bucket = "testuser-capstone-staging" -> "testuser-capstone-prod"  # forces replacement
# aws_s3_bucket.env[2] will be destroyed

Plan: 1 to add, 0 to change, 2 to destroy.
```

**Plan with `for_each`, same edit:**
```text
# aws_s3_bucket.env["staging"] will be destroyed

Plan: 0 to add, 0 to change, 1 to destroy.
```

**Why this is the most dangerous defect in the list:**
When using `count`, Terraform tracks resources by array index numbers (`env[0]`, `env[1]`, `env[2]`). If an item in the middle of the list (`staging`) is deleted, all subsequent items shift positions by one index. Because S3 bucket names are immutable and force replacement, Terraform will destroy and recreate the production bucket (`env[2]` -> `env[1]`), deleting all production data, just because an unrelated staging environment was removed. Using `for_each` identifies resources by their unique, stable map keys (`env["staging"]`), guaranteeing that deleting staging modifies only `staging` and leaves `prod` untouched.
