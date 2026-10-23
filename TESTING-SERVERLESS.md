# Testing the serverless deployment with Taskboard

This walks through testing every serverless part of the Deploy tab with the Taskboard app in this folder. It covers AWS Lambda + API Gateway first, then ECS on Fargate.

**Do the [Appendix](#appendix-configure-and-run-the-app-locally) first.** It gets the app running on your machine and committed to git. The extension only deploys code that is committed and pushed.

Why not fitness-tracker: it keeps its data in a SQLite file inside the app folder. Lambda's disk is read-only, and SQLite can't exercise an AWS database. Taskboard uses PostgreSQL, so it tests the real thing: an RDS database, migrations, backups and recovery.

---

## What you'll test

| Test | What it proves | Time |
|---|---|---|
| [1. Lambda: frontend, API, database](#test-1--lambda-frontend-api-and-database) | Network, RDS, migrations, Lambda + Web Adapter, API Gateway, S3 + CloudFront | 45–60 min (first deploy is slow) |
| [2. Change, redeploy, roll back](#test-2--change-redeploy-roll-back) | Versions, releases, Roll back release | 20 min |
| [3. S3 export and SQS events](#test-3--s3-export-and-sqs-events) | Services that use the app's role instead of passwords | 20 min |
| [4. Lambda functions](#test-4--lambda-functions) | All 4 triggers, Test locally, Invoke, Logs, Roll back, failed-events queue | 45 min |
| [5. Backups and recovery](#test-5--backups-and-recovery) | Back up data, Recover data | 30 min |
| [6. A failing deploy on Lambda](#test-6--a-failing-deploy-on-lambda) | What happens when a health check fails | 15 min |
| [7. ECS on Fargate](#test-7--ecs-on-fargate) | Switching to Fargate, load balancer, automatic rollback | 40 min |
| [8. Custom domain (optional)](#test-8--custom-domain-optional) | HTTPS on your own domain | 30 min |
| [9. Remove compute and clean up](#test-9--remove-compute-and-clean-up) | Remove compute keeps data; deleting everything | 20 min |

**Cost.** While these tests run, your AWS account pays for:
- an RDS database;
- two NAT gateways (they exist because the Lambda talks to a private database);
- in Test 7, a load balancer and a Fargate task.

That's roughly a few US dollars per day. Do Test 9 when you're finished.

---

## Before you start (once)

1. **Run the app locally and commit it.** Follow the [Appendix](#appendix-configure-and-run-the-app-locally).

2. **Install the extension built from the `deploy-tab-ext` branch.**
   - Your extension repository is on `main` at the moment, and `main` has no Deploy tab.
   - In VS Code: Extensions → `...` → **Install from VSIX…**.
   - Pick the `localcode-1.0.6-*.vsix` build from `C:\Users\AnukulParajuli\sdlc\Extension\My_Extension\localcode` that matches the backend you use (`-local`, `-dev`, or the production one).

3. **SDLCForge backend and web UI.** They must include the serverless deployment-plan changes (the AWS managed services list and the serverless compute choices).

4. **AWS.** You need:
   - an AWS account and a region (e.g. `ap-southeast-2`);
   - the **deploy IAM user** whose access keys you enter in the Deploy tab (the same one you used for the VM is fine);
   - a way to sign in to the AWS console **as an administrator**, needed once per permissions update (step 1.5).

5. **GitHub.** Your token is already set in the Repositories tab, as for fitness-tracker.

6. **Docker Desktop** must be running, for **Test locally** on functions.

7. **Open the `taskboard` folder in VS Code** and connect it to an SDLCForge project, the same way you did for fitness-tracker.

---

## Test 1 – Lambda: frontend, API and database

### 1.1 The deployment plan (web UI)

In the project's **Deployment** stage:

1. **Cloud:** AWS. **Region:** your region.
2. **Deployment type:** Serverless.
3. **Backend compute:** AWS Lambda + API Gateway.
4. **Frontend hosting:** S3 + CloudFront.
5. **Secrets store:** SSM Parameter Store.
6. **AWS managed services:** add one service:
   - kind **RDS PostgreSQL**;
   - name `app-db`;
   - mode **Create**.
7. **Environments:** at least `dev`.
8. **Save.**

### 1.2 Step 1 – Source code

1. The `taskboard` row appears.
2. Use the row to **create the GitHub repository** (choose private) and **push**.
3. The row must end up synced: nothing uncommitted, not behind.

### 1.3 Step 2 – Infrastructure

Check what the tab detected. App names come from the folder names.

| App | Expect |
|---|---|
| `frontend` | Static frontend · build `npm run build` · output `dist` · route `/` |
| `backend` | Python (FastAPI) · start `uvicorn main:app --host 0.0.0.0 --port $PORT` · port 8000 · route `/api` · **Strip prefix off** (its routes already start with `/api`) |

Under **backend**:
- **Databases:** `app-db` is used, with `DATABASE_URL` set to its **url** field.
- **Run its migration on each deploy** is ticked, with the command `alembic upgrade head` (an *Alembic* chip). The tab finds `backend/alembic.ini`.

**Lambda** settings:
- web app memory **512**;
- request timeout **30**;
- **web app maximum concurrency 10**. Each Lambda copy opens its own database connections, and this keeps the small database within its limit.
- **Container health path:** `/api/health`. This is the path the app itself answers.

**AWS managed data → app-db settings:** the defaults are fine (db.t3.micro, 20 GB). For an easier clean-up, you can turn **deletion protection off**, since this is a test.

Click **Generate**. It writes the infrastructure repository into `taskboard\infra\`, which `taskboard`'s `.gitignore` excludes because it's a separate git repository.

### 1.4 Find your namespace

Open `taskboard\infra\sdlcforge.json` and note the value of `"namespace"`, e.g. `taskboard-3fa9c01b2e`.

Every AWS resource is named `<namespace>-dev-…`. Use the namespace to find things in the AWS console.

### 1.5 AWS permissions: the step you haven't done yet

**Why it's needed.** The pipeline creates IAM roles for your app and functions. The deploy user is allowed to create those roles only if each one carries a ceiling, the **runtime boundary**, a policy named `<namespace>-runtime-boundary`. The deploy user can't create that policy or its own permissions; that's the point. So an administrator creates them once.

Every deploy first checks that the boundary exists. Without it, Validate and Deploy stop with:

> The IAM permissions boundary … does not exist … Run iam/setup.sh in AWS CloudShell

Generate wrote these files to `taskboard\infra\iam\`:

| File | What it is |
|---|---|
| `deployment-1.json`, `deployment-2.json`, … | What the deploy user may do, split into parts because each AWS policy is limited to 6,144 characters |
| `runtime-boundary.json` | The ceiling for every role the pipeline creates |
| `setup.sh` | Creates or updates all of them and attaches the deployment parts to your user |
| `README.md` | The same instructions |

**Option A, recommended: `setup.sh` in CloudShell**

1. Sign in to the AWS console as an administrator.
2. Click the **CloudShell** icon (`>_`) in the top bar. Any region works.
3. **Actions → Upload file** → choose `taskboard\infra\iam\setup.sh`.
4. Run it with the deploy user's name:
   ```bash
   bash setup.sh your-deploy-user-name
   ```
   If you're not sure of the user name, use the access key ID from step 3 of the Deploy tab:
   ```bash
   aws iam get-access-key-last-used --access-key-id AKIA...
   ```
5. Expected output ends with:
   ```
   Done: N deployment policies are attached to your-deploy-user-name, and the runtime boundary <namespace>-runtime-boundary exists.
   ```

**Option B: by hand in the IAM console, using the JSON files**

1. Find your 12-digit account id: the account menu, top right.
2. IAM → **Policies → Create policy → JSON**.
   - Paste `runtime-boundary.json`, replacing every `ACCOUNT_ID` with your account id.
   - Name it **exactly** `<namespace>-runtime-boundary`.
3. Repeat for each `deployment-N.json`, named `<namespace>-deploy-N`.
4. IAM → **Users** → your deploy user → **Add permissions → Attach policies directly** → tick each `<namespace>-deploy-N` → Add.

   Don't attach the boundary to the user. It only has to exist.

**Check it worked**
- IAM → Users → your user → Permissions lists `<namespace>-deploy-1 … N`. The VM policies you added earlier (EC2, S3, ECR) can stay.
- IAM → Policies, filtered by *Customer managed*, lists `<namespace>-runtime-boundary`.
- If AWS says the user has reached 10 managed policies, detach one it no longer needs and run again.

**Run it again whenever Generate adds something**: a database, S3 or SQS, functions, Fargate, a domain. It updates the same policies in place. This guide says so at each test.

### 1.6 Step 3 – Secrets

1. Enter the deploy user's **AWS access key ID** and **secret access key**. Each project has its own infrastructure repository, so this project needs them too.
2. `APP_DB_PASSWORD`: click **Generate**. It's the RDS master password; it's made on your computer and stored only in the vault and GitHub.
3. **Leave `DATABASE_URL` empty for `dev`.** The binding to `app-db` fills it in at deploy time. A value typed here would override the binding and point the app at the wrong database.
4. No SSH key is needed for serverless.
5. **Sync.**

### 1.7 Step 4 – Validate, then Deploy

1. Environment **dev** → **Validate**.
   - Expected: success, with a message like "Foundation planned; application definitions validated".
   - If it says the permissions boundary is missing, redo 1.5.
2. **Deploy.**
   - The first run takes about 25–40 minutes: the network and RDS take 10–20 minutes, CloudFront 5–15.
   - Follow it with **View the run on GitHub**. The single job **Application** shows groups like "Create or update the foundation", "Build application images", "Snapshot data and apply migrations", "Deploy application compute" and "Publish frontend assets".

### 1.8 What to check

**In the Deploy tab:** the run is green and shows a URL like `https://d1a2b3c4.cloudfront.net`.

**In the app (open the URL):**
- The header shows **version 1.0.0 · AWS Lambda · database: connected · S3 export off · SQS events off**.
- Add three tasks, move them between columns, delete one, then reload the page. Everything is still there because it's stored in RDS.
- DevTools → Network: calls go to `/api/tasks` on the **same address** and return 200.
- Open `<URL>/api/health`. It shows `{"status":"ok","version":"1.0.0"}`.
- **Cold start:** leave the page closed for about 20 minutes, then reload. The badges take a second or two longer the first time, then they're fast. That's Lambda starting a new copy.

**In the AWS console** (your region; search for your namespace):

| Where | What you should see |
|---|---|
| **Lambda → Functions** | a function `<namespace>-dev-…`. **Aliases:** `live`. **Configuration → VPC:** private subnets (because it uses RDS). **Concurrency:** 10 reserved. |
| **API Gateway → APIs** | an HTTP API with routes `ANY /api` and `ANY /api/{proxy+}` |
| **CloudFront** | a distribution. Its behaviours send `/api*` to API Gateway and everything else to S3. |
| **S3** | a frontend bucket with `index.html` and `assets/` |
| **RDS → Databases** | `<namespace>-dev-…`: Available, **Publicly accessible: No** |
| **VPC → NAT gateways** | two, Available |
| **CloudWatch → Log groups** | `/sdlcforge/<namespace>-dev/backend` holds the API's logs, plus the migration's log stream with "Running upgrade -> 0001, Create the tasks table." |
| **The run result** | a snapshot ARN for `app-db`, taken just before the migration |

---

## Test 2 – Change, redeploy, roll back

1. In `backend/main.py` change `APP_VERSION = "1.0.0"` to `"1.1.0"`. Commit and push (Source Control). Step 1's row becomes synced again.
2. Step 4 → **Deploy.** When it finishes, the header shows **version 1.1.0**. In the Lambda console, the `live` alias now points at version 2.
3. Step 4 → **Roll back release** → choose the release from Test 1.
   - The header shows **1.0.0** again.
   - Your tasks are unchanged, because data is never rolled back.
   - The release list gains a new entry: the rollback itself.
4. **Deploy** again to return to the code at your latest commit (1.1.0).

Every deploy re-runs the migration, which does nothing because the database is already up to date, and takes a fresh RDS snapshot first. See Test 9 for deleting those snapshots.

---

## Test 3 – S3 export and SQS events

These services need no password: the app reaches them through its **IAM role**, so no AWS keys are ever given to the app.

1. **Web UI → AWS managed services:** add
   - **S3**, name `files`, Create;
   - **SQS**, name `task-events`, Create.

   Save.
2. **Step 2 → backend → bindings:**
   - `S3_BUCKET` → `files` → **bucket**;
   - `SQS_QUEUE_URL` → `task-events` → **queue_url**.

   Add them if they aren't bound automatically. Then **Generate**.
3. **Permissions:** run `setup.sh` again (1.5). New services mean new permissions.
4. **Deploy.**
5. **Check:**
   - The header shows **S3 export on · SQS events on**.
   - Click **Export to S3**. It shows "Exported to s3://…/exports/tasks-….json". S3 console → the `files` bucket → `exports/` contains the file.
   - Add a task, then SQS console → `<namespace>-dev-…` (the task-events queue) → **Send and receive messages → Poll for messages**. A `task.created` message is there.

     After Test 4 adds a function that reads this queue, messages disappear quickly, because the function consumes them.

---

## Test 4 – Lambda functions

Functions are created in the `taskboard` repository, under `functions/`. Their settings go in `.sdlcforge/functions.json`.

### 4.1 Create four functions (Step 1 → Create a Lambda function)

| Name | Language | What starts it | Answer the prompts with |
|---|---|---|---|
| `export-watcher` | Python | A file uploaded to S3 | bucket `files`, folder `exports/` |
| `task-worker` | Python | An SQS queue message | queue `task-events` |
| `heartbeat` | JavaScript | A schedule | `rate(5 minutes)` |
| `hello` | Python | An HTTP request | method `GET`, path `/fn/hello` |

Each one gets:
- working starter code for its trigger;
- `events/<trigger>.json`, a sample event shaped like AWS's;
- an entry in `.sdlcforge/functions.json`.

### 4.2 Test locally

On each function card, click **Test locally**. Docker must be running.

The **SDLCForge: functions** output panel shows the function running in AWS's own Lambda image, with its sample event, and its result. For example, `task-worker` returns `{"batchItemFailures": []}`.

### 4.3 Deploy them

1. Commit and push `functions/` and `.sdlcforge/functions.json`.
2. Step 2 → **Generate**, then run `setup.sh` again (1.5).
3. **Deploy.**

### 4.4 Check each one

Every card now shows a **version**, plus **Invoke**, **Logs** and **Roll back**.

| Function | How to check |
|---|---|
| `export-watcher` | In the app, click **Export to S3**. Card → **Logs** shows the uploaded file's key. |
| `task-worker` | In the app, add a task. Its Logs show the `task.created` message. |
| `heartbeat` | Its Logs show a new entry every 5 minutes. |
| `hello` | Open `<URL>/fn/hello`; it returns the function's JSON. Also try **Invoke** on its card: the reply appears in the run result. |

### 4.5 Roll back one function

1. Change the message in `functions/hello/lambda_function.py`, push, and **Deploy**. `<URL>/fn/hello` shows the new message, and the card shows version 2.
2. Card → **Roll back** → choose version 1. Within seconds, `/fn/hello` shows the old message. Nothing is rebuilt: only the `live` pointer moves.

### 4.6 Failed events

1. In `functions/export-watcher/lambda_function.py`, make the handler fail by adding this as its first line:
   ```python
   raise Exception("test failure")
   ```
   Push and **Deploy**.
2. In the app, click **Export to S3**.
3. AWS retries the event twice over a few minutes, then moves it to the function's **failed-events queue**.
   - The card's count refreshes after each deploy, so **Deploy** once more. The card then says "1 failed event is kept in its failed-events queue".
   - Or check SQS → the queue named `<namespace>-dev-…` that belongs to export-watcher → Poll for messages.
4. Remove the `raise` line, push, and Deploy.

When you're done, change `heartbeat` to `rate(1 day)` or delete it, so it isn't invoked every 5 minutes.

---

## Test 5 – Backups and recovery

1. Step 4 → **Back up data.** The run result lists a snapshot ARN for `app-db`, and a note for `files` (S3 keeps every version of every file, so there's nothing to copy). Copy the ARN.
2. In the app, delete a task so you can tell the copies apart.
3. Step 4 → **Recover data** → choose `app-db` → paste the ARN.
   - The run creates a **new** database named `<namespace>-restore-…`, which takes 10–20 minutes.
   - RDS → Databases shows both. The live `app-db` is untouched, and the app still shows your latest tasks.
   - Recovery never overwrites live data. To actually use the copy, you'd add it in the web UI as an *Existing* service and bind the app to it. You don't need to do that for this test.
4. Delete the recovered database: RDS → select it → Actions → **Delete**, without a final snapshot.

---

## Test 6 – A failing deploy on Lambda

1. **Step 3:** add the variable `HEALTH_FAIL` = `true` for `dev`, then **Sync**.
2. **Deploy.**
3. **Expected:**
   - The run fails with "its Lambda web health check failed".
   - The frontend files stay as they were.
   - **Known limitation:** on Lambda the new version is already live when the check runs, so the app's API calls now fail.
4. **Recover:**
   1. Step 3 → **delete `HEALTH_FAIL`** → **Sync**. If you don't, the next deploy fails again.
   2. Step 4 → **Roll back release** → choose the last good release.
   3. The app works again.

---

## Test 7 – ECS on Fargate

The same app, now on always-running containers behind a load balancer. Data, functions and services stay as they are.

1. **Web UI:** change **Backend compute** to **Amazon ECS on Fargate**, then Save.
2. **Step 2 → Fargate:**
   - CPU **256**, memory **512**;
   - minimum tasks **1**, maximum **2**;
   - container health path `/api/health`.

   **Generate**, then run `setup.sh` again (1.5): Fargate and the load balancer need new permissions.
3. **Deploy.** The Lambda web app is removed, and an ECS service, a load balancer and the Fargate task are created.
4. **Check:**
   - The app's header shows **ECS on Fargate**, and your tasks are still there.
   - ECS → Clusters → `<namespace>-dev` → Services: 1 running task.
   - EC2 → **Target groups** → the backend's group shows its target as **healthy**.
   - EC2 → **Load balancers**: one, active.
   - CloudWatch log group `/sdlcforge/<namespace>-dev/backend` now shows the container's logs.
   - Functions from Test 4 keep working: they stay on Lambda.
5. **A failing deploy on Fargate:**
   1. Step 3 → `HEALTH_FAIL=true` → Sync → **Deploy**.
   2. Expected: ECS starts a new task, it fails its health checks, and ECS's circuit breaker stops the rollout. **The old task keeps serving**, so the app keeps working throughout.
   3. **Please note whether the run is reported as failed.** This is the one path not yet tested on real AWS.
   4. Then delete `HEALTH_FAIL` → Sync → Deploy.
6. **Optional:** set minimum tasks to 2 → Generate → Deploy. Two tasks run, in two zones.

To go back to Lambda, change Backend compute again, then Generate, run `setup.sh`, and Deploy.

---

## Test 8 – Custom domain (optional)

Both Lambda and Fargate serve your domain through CloudFront. Production gets the domain itself (`app.example.com`); other environments get a prefix (`dev.app.example.com`). Pick **one** of these two ways.

### Way A – automatic, with a Route 53 hosted zone

1. Route 53 → **Hosted zones → Create hosted zone** → `app.example.com`, Public. Note its **zone id** (`Z…`) and its 4 **NS** values.
2. Where your domain's DNS lives (Cloudflare, Hostinger…), add 4 records: type **NS**, name `app`, one per value. This hands `app.example.com` to Route 53.
3. Check the hand-over: `nslookup -type=NS app.example.com` should list `awsdns` servers.
4. **Step 2:**
   - Domain `app.example.com`;
   - **Network and domain settings → Route 53 hosted zone id** `Z…`;
   - certificate left empty.

   **Generate**, run `setup.sh`, **Deploy**.
5. The pipeline does the rest:
   - asks AWS for a certificate for `dev.app.example.com`;
   - proves the domain is yours via a DNS record;
   - attaches the certificate to CloudFront;
   - points the name at CloudFront.
6. **Check:** `https://dev.app.example.com` works, and ACM (region **US East (N. Virginia)**) shows the certificate as *Issued*.

### Way B – keep DNS at Cloudflare or Hostinger

1. ACM, region **US East (N. Virginia)** → **Request** a public certificate.
   - Names: `app.example.com` and `*.app.example.com`.
   - Validation: DNS.
2. Add the CNAME records ACM shows at your DNS host.
   - On Cloudflare, set them to **DNS only** (grey cloud).
   - Wait for *Issued*, and keep those records: renewal needs them.
3. **Step 2:** Domain `app.example.com`, **Issued ACM certificate ARN** = the certificate's ARN, hosted zone empty. **Generate**, run `setup.sh`, **Deploy**.
4. **Add the DNS record for the site.** The tab doesn't show CloudFront's address yet, so get it from the console:
   1. CloudFront → find the distribution whose *Alternate domain names* shows `dev.app.example.com`.
   2. Copy its domain name (`d1a2b3c4.cloudfront.net`).
   3. At your DNS host, add a **CNAME**: name `dev.app` → `d1a2b3c4.cloudfront.net`. On Cloudflare, DNS only.
5. **Check:** `https://dev.app.example.com` works.

### Checking any domain

Check the name resolves:
```bash
nslookup dev.app.example.com
```

Check the site answers over HTTPS:
```bash
curl -sI https://dev.app.example.com
```

Check the certificate (names, issuer, expiry):
```bash
openssl s_client -connect dev.app.example.com:443 -servername dev.app.example.com </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

---

## Test 9 – Remove compute and clean up

1. Step 4 → **Remove compute** for `dev`. When it finishes:
   - **Removed:** the URL stops working; the Lambda functions, API Gateway, CloudFront, ECS service, load balancer and NAT gateways are gone.
   - **Kept:** RDS, the `files` bucket, the SQS queues, image repositories, logs, roles. A later **Deploy** brings everything back on top of the same data.
2. To stop all costs after testing, delete what Remove compute keeps, in the AWS console:
   - **RDS:** if deletion protection is on, Modify → turn it off → Apply immediately. Then Actions → Delete (no final snapshot).
   - **RDS → Snapshots → Manual:** delete the snapshots the deploys and Test 5 created. They're billed for storage.
   - **S3:** the `files` bucket → **Empty**, which removes every old version too → **Delete**.
   - **SQS:** delete `task-events`, its `-dead` queue, and the functions' failed-events queues.
   - **Secrets Manager:** delete `/sdlcforge/<namespace>-dev/app-db`.
   - **Systems Manager → Parameter Store:** delete the `/sdlcforge/<namespace>-dev/…` parameters.
   - **Optional, no cost:** ECR repositories, CloudWatch log groups, IAM roles named `<namespace>-dev-…`, and the VPC. The VPC is free once its NAT gateways are gone.

---

## If something goes wrong

| What you see | What it means / what to do |
|---|---|
| "The IAM permissions boundary … does not exist" | Do step 1.5 |
| "AccessDenied" / "not authorized to perform …" during a deploy | Generate added something; run `setup.sh` again |
| "generate a database password in the Secrets step" | Step 3 → generate `APP_DB_PASSWORD` → Sync |
| Header says **database: unavailable** | `DATABASE_URL` is set by hand in step 3 (delete it), or the binding is missing (step 2) |
| "its Lambda web health check failed" | `/api/health` didn't answer: check the health path is `/api/health`, `HEALTH_FAIL` isn't set, and the backend's CloudWatch logs |
| Migration failed | CloudWatch → backend log group → the migration log stream. The new version wasn't started. |
| "Lambda environment exceeds 4096 bytes" | Too many or too long variables for a Lambda; move big values into Secrets Manager |
| Fargate target unhealthy | Health path wrong, or the app isn't listening on `$PORT` |
| Page loads but `/api` calls fail with 403/404 from CloudFront | The run didn't finish (frontend published before the API?), or the backend route isn't `/api`. Check step 2. |

Please tell me what you see in Test 6 and Test 7.5 (failing deploys), and anything that doesn't match this guide.

---

## Appendix: configure and run the app locally

Do this before using the extension.

### What you need
- **Node.js 20 or 22**: `node --version`.
- **Python 3.12**: `python --version`. 3.12 is what the deployed image uses. A newer Python may lack ready-made packages for the PostgreSQL driver.
- **Docker Desktop**, running. It provides the local PostgreSQL.
- **Git.**

### A1. Start PostgreSQL in Docker
```bash
docker run -d --name taskboard-db -e POSTGRES_USER=taskboard -e POSTGRES_PASSWORD=taskboard -e POSTGRES_DB=taskboard -p 5432:5432 postgres:16
```
- If port 5432 is already taken, use `-p 5433:5432` and change the port in `backend/.env` (next step).
- Later: `docker stop taskboard-db` / `docker start taskboard-db`.

### A2. Backend

From `C:\Users\AnukulParajuli\codes\taskboard\backend`:

```bash
python -m venv .venv
source .venv/Scripts/activate        # Git Bash.  PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                 # PowerShell: copy .env.example .env
alembic upgrade head                 # creates the tasks table
uvicorn main:app --reload --port 8000
```
- `alembic upgrade head` should print `Running upgrade  -> 0001, Create the tasks table.`
- Then open http://127.0.0.1:8000/api/health → `{"status":"ok","version":"1.0.0"}`.
- And http://127.0.0.1:8000/docs → the API's interactive docs.

### A3. Frontend

In a second terminal, from `C:\Users\AnukulParajuli\codes\taskboard\frontend`:

```bash
npm install
npm run dev
```

Open http://localhost:5173.
- The header shows **version 1.0.0 · local or server · database: connected · S3 export off · SQS events off**.
- Add, move and delete tasks. Stop and restart the backend: the tasks are still there.

Check that the production build works, the same build the pipeline runs:
```bash
npm run build
```
It writes `frontend/dist/`, which git ignores.

### A4. Commit (the Deploy tab pushes it in step 1)

From `C:\Users\AnukulParajuli\codes\taskboard`:

```bash
git init
git add .
git commit -m "Taskboard test app"
```
- `npm install` created `frontend/package-lock.json`. Commit it: the image build uses `npm ci`, which needs it.
- `backend/.env`, `.venv/`, `node_modules/` and `dist/` are ignored by `.gitignore` and never committed.

Now go back to [Before you start](#before-you-start-once).
