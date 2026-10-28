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
| [3. S3 export and SQS events](#test-3--s3-export-and-sqs-events) | Services that use the app's role instead of passwords | 30–40 min |
| [4. Lambda functions](#test-4--lambda-functions) | All 4 triggers, Test locally, Invoke, Logs, Roll back, failed-events queue | 45 min |
| [5. Backups and recovery](#test-5--backups-and-recovery) | Back up data, Recover data | 30 min |
| [6. A failing deploy on Lambda](#test-6--a-failing-deploy-on-lambda) | What happens when a health check fails | 15 min, plus 20 to switch back from Fargate |
| [7. ECS on Fargate](#test-7--ecs-on-fargate) | Switching to Fargate, load balancer, automatic rollback | 40 min |
| [8. Custom domain (optional)](#test-8--custom-domain-optional) | HTTPS on your own domain | 30 min |
| [9. Remove compute and clean up](#test-9--remove-compute-and-clean-up) | Remove compute keeps data; deleting everything | 45–60 min |

**Already done Tests 1, 2 and 7?** Then the app runs on Fargate. Continue in this order:
1. Tests 3, 4 and 5: they work on Fargate as it is.
2. Test 6: it starts by switching back to Lambda.
3. Test 8, which is optional.
4. Test 9.

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

## Where things are (read this once before Test 3)

Tests 3 to 9 send you to four places. This is what each one means.

**The web UI** is the SDLCForge website.
- Open your project (`taskboard-test`) and click its **Deployment** stage.
- A change there is kept only after you click **Save configuration**.

**The Deploy tab** is in the SDLCForge panel in VS Code.
- At the top of the tab are four numbered circles: **1 Source code**, **2 Infrastructure**, **3 Secrets** and **4 Deploy**. When this guide says "open Step 2", click the circle **2 Infrastructure**.
- Above the circles is the **Deployment plan** card. Its **↻ Sync from web UI** button reads the plan again, after you've saved a change in the web UI.

**The AWS console** is https://console.aws.amazon.com.
- Check that the region at the top right is **Asia Pacific (Sydney)**, which is `ap-southeast-2`.
- To open a service such as S3, SQS or RDS, type its name in the search box at the top of the page and click it in the results.

**CloudShell** is a terminal inside the AWS console.
- Open it with the `>_` icon in the console's top bar.
- Its **Actions** menu, at the top right of the terminal, has **Upload file**.

**Your namespace.** It's `taskboard-767fbab00b` (you can see it in `infra\sdlcforge.json`). Every AWS resource of the dev environment has a name that starts with `taskboard-767fbab00b-dev`. Typing that into the search box of any AWS console page finds your resources.

---

## Test 3 – S3 export and SQS events

**If you've just done Test 7,** the app runs on ECS on Fargate. That's fine:
- Tests 3, 4 and 5 work the same on Fargate as on Lambda. The only difference is that the app's header says "ECS on Fargate" instead of "AWS Lambda".
- Test 6 needs Lambda, and starts by switching back to it.

**Before you start, check that the failure switch from Test 7 is off.**
1. Open Step 3 in the Deploy tab.
2. Under **App variables**, find the row `HEALTH_FAIL`. It's always in the list, because the backend's code reads it.
3. Look at the badge on its right:
   - **• Not set** (blue) means the switch is off. That's what you want, and there's nothing to do.
   - A green badge with **Change** and **Delete** buttons next to it means Test 7 left it on. Click **Delete**, then click **Delete** again in the confirmation. Otherwise every deploy fails.

### 3.1 What S3 and SQS are, and what this test does

**S3 (Simple Storage Service)** is AWS's file storage.
- Files are kept in a **bucket**.
- Each file has a path inside the bucket, such as `exports/tasks-20261027T101500Z.json`.
- The bucket this test creates is private and encrypted.
- It also keeps every older version of a file when the file is replaced or deleted. This is called *versioning*.

**SQS (Simple Queue Service)** is a message queue: a mailbox for programs. One program puts messages in, and another program takes them out later.
- In Taskboard, the backend puts a message in the queue every time you add a task. The message says which task was created.
- The message waits in the queue, for up to 4 days, until something reads it and deletes it.
  - In this test, you read the messages yourself in the AWS console.
  - In Test 4, a Lambda function does it automatically.
- Apps use queues so that slow work, like sending an email, happens in the background. The user doesn't have to wait for it.
- The pipeline also creates a second queue, whose name ends in `-dead`. This is the **dead-letter queue**. If a message is read 5 times and never deleted, SQS moves it there, so a message that keeps failing doesn't block the others.

**How the backend finds them.** The Taskboard backend already contains the code for both features (in `backend/aws.py`). It turns each feature on only when a variable is set:

| Variable | What it contains | What it turns on |
|---|---|---|
| `S3_BUCKET` | the bucket's name | the **Export to S3** button |
| `SQS_QUEUE_URL` | the queue's address | a message for every task you add |

**You never type these values.** In Step 2 you tick a box that connects the bucket and the queue to the backend, and the deploy fills in the real values.

**No passwords are needed.** The backend runs with an AWS identity of its own, called an **IAM role**. The deploy gives that role permission to use this bucket and this queue, and nothing else. So you don't add anything in Step 3 (Secrets) for this test, and you should never put AWS access keys there for the app.

### 3.2 Add a bucket and a queue in the web UI

1. Open the web UI, open your project, and click its **Deployment** stage.
2. Scroll down to the section **AWS managed services**. It already has one card: `app-db`, the database from Test 1.
3. Below the cards is a dropdown that says **+ Add an AWS managed service**. Click it and choose **S3 files**. A new card appears.
4. On the new card:
   1. The first box is the name. It's filled in with something like `s3`. Delete that and type `files`.
   2. Leave the second box on **S3 files**.
   3. Leave the third box on **Create**.
5. Click the **+ Add an AWS managed service** dropdown again, and choose **SQS queue**.
6. On this new card, change the name to `task-events`. Leave the second box on **SQS queue**, and the third box on **Create**.
7. Click **Save configuration**.

Type the names exactly as `files` and `task-events`, because Test 4 uses them.

**About the "Queue URL" and "Queue ARN" boxes.** You only see them if you change the third box to **Existing**.
- **Existing** means: "I already have a queue in AWS; use that one". The form then needs its address.
- **Create** means the deploy makes a new queue and finds its address by itself. So with **Create**, you don't need a URL or an ARN at all.

Section 3.10 explains where to see the address after the deploy, if you're curious.

### 3.3 Load the new plan into VS Code

1. In VS Code, open the Deploy tab.
2. In the **Deployment plan** card at the top, click **↻ Sync from web UI**.
3. The card now mentions `files` and `task-events`, as well as `app-db`.

### 3.4 Connect the bucket and the queue to the backend

1. Open Step 2 (click the circle **2 Infrastructure**).
2. Scroll to the **Apps** section and find the card for **backend**.
3. Inside that card, find the heading **Databases it uses**.
   - Despite the heading, it lists every AWS service in the plan, each with a checkbox: `app-db`, `files` and `task-events`.
   - `app-db` is already ticked.
4. Tick the box next to **files**, if it isn't ticked already.
   - A small label appears under it: `S3_BUCKET ← bucket`. It means the backend gets the bucket's name in the variable `S3_BUCKET`.
   - You may see a couple more labels, such as `S3_REGION ← region`. They don't matter.
5. Tick the box next to **task-events**.
   - The label `SQS_QUEUE_URL ← queue_url` appears. It means the backend gets the queue's address in the variable `SQS_QUEUE_URL`.
6. **Only if a label shows a different variable name:**
   1. Click the **Variables…** button next to it. A text box opens at the top of VS Code.
   2. Replace the text: type `S3_BUCKET=bucket` for files, or `SQS_QUEUE_URL=queue_url` for task-events.
   3. Press Enter.
7. Scroll down to the **Infrastructure repository** section, at the bottom of Step 2. It has a box called **AWS managed data**, which lists the three services.
   - Each line should end with the word `backend`.
   - If a line says `not bound yet` instead, that service's box from item 4 or 5 isn't ticked.

### 3.5 Generate the infrastructure and push it

1. Still in Step 2, in the **Infrastructure repository** section, click **⚙ Generate again**.
   - If the button says **⚙ Regenerate** instead, the deploy settings didn't notice your ticks. Go back to 3.4 and check them.
2. After a few seconds, the line above the button turns green and says that `infra/` matches these settings.
3. Just below the button is the row for the **infra** repository. It now says *1 commit to push*, and has a **Push 1 commit** button. Click it.
4. Wait until the row says **Synced**.

### 3.6 Give the deploy user the new AWS permissions

**Why this is needed.** The IAM user whose keys the deploy uses isn't yet allowed to create buckets and queues. Generate wrote an updated `setup.sh`, and an administrator has to run it once.

1. In a browser, sign in to the AWS console as an **administrator**, not as the deploy user.
2. Click the `>_` icon in the top bar to open CloudShell. Wait until you see a prompt.
3. Type `rm -f setup.sh` and press Enter. This deletes the old copy from Test 1, so you can't run the old one by mistake.
4. Open the **Actions** menu at the top right of CloudShell, and choose **Upload file**.
5. Choose the file `C:\Users\AnukulParajuli\codes\taskboard\infra\iam\setup.sh`, then click **Upload**.
6. Type the line below, with your deploy user's name in place of `your-deploy-user-name`, and press Enter. (The deploy user is the IAM user whose access keys are in Step 3.)
   ```bash
   bash setup.sh your-deploy-user-name
   ```
7. Wait until the last line starts with `Done:`. It says how many policies are attached to your user.

If you skip this, the deploy in the next section fails with an error that contains `AccessDenied` and `s3:CreateBucket` or `sqs:CreateQueue`.

### 3.7 Deploy

1. Open Step 3 (click the circle **3 Secrets**). You don't need to add or set anything here. Under **App variables**, check these three rows:
   - **`S3_BUCKET`** now says **✓ from files on AWS**.
   - **`SQS_QUEUE_URL`** now says **✓ from task-events on AWS**. Before you did 3.4 and 3.5, both rows said **• Not set**. Don't click **Set** on either one: the deploy fills them in.
   - **`HEALTH_FAIL`** still says **• Not set**.
2. Open Step 4 (click the circle **4 Deploy**). Check that the **Environment** dropdown says **dev**.
3. Click **🚀 Deploy**.
   - A run box appears under the buttons, with the status **Running**.
   - To see more detail while it runs, click **View the run on GitHub** in that box.
4. Wait about 10 to 20 minutes, until the status says **Succeeded**.
5. Under the buttons, a new line now says *Retained data: app-db (rds_postgresql), files (s3), task-events (sqs)*.

### 3.8 Check the export to S3

1. Open the app. Its address is shown after **App:** in the run box. Reload the page once it's open.
2. Look at the labels in the header. The last two now say **S3 export on** and **SQS events on**, in green. If either one says **off**, see 3.11.
3. If the board is empty, add two or three tasks.
4. Click **Export to S3**. A line appears under the form, like this:
   ```
   Exported to s3://taskboard-767fbab00b-dev-123456789012-ab12cd34/exports/tasks-20261027T101500Z.json
   ```
   The text between `s3://` and `/exports` is the bucket's name.
5. In the AWS console, open **S3**. In the list of buckets, click the bucket with that name.
   - A second bucket also starts with your namespace. That's the frontend's bucket: it holds `index.html` and an `assets` folder.
6. Click the **exports/** folder, then click the file inside it.
7. Click **Open** at the top right. The file opens: a list of your tasks in JSON.

### 3.9 Check the messages in SQS

1. In the app, add a task named `queue test`.
2. In the AWS console, open **Simple Queue Service** (type `SQS` in the search box). You see a list of queues.
3. In the search box above that list, type `taskboard-767fbab00b-dev`. Two queues appear:
   - The one whose name ends in `-dead` is the dead-letter queue.
   - The other one is **task-events**. Its name ends in a short code instead of the word "task-events". That's normal.
4. Look at the **Messages available** column for task-events. It's at least 1. It goes up by one for every task you add, though it can take a minute to update.
5. Click the name of the task-events queue. Its page opens. The **Details** box at the top shows its **URL** and its **ARN**.
6. Click the **Send and receive messages** button at the top right.
7. Scroll down to the **Receive messages** section and click **Poll for messages**. For about 20 seconds, AWS collects messages. Your message appears in a list underneath.
8. Click the message's ID. A window opens.
9. Its **Body** tab shows the message:
   ```json
   {"event": "task.created", "task": {"id": 7, "title": "queue test", "status": "todo", "created_at": "…"}}
   ```
   Click **Done** to close the window.
10. To remove the message from the queue, tick the box next to it, click **Delete**, and then click **Delete** again in the confirmation.

**Three things that can surprise you here:**
- **A message you polled disappears for about 3 minutes.** While someone is reading a message, SQS hides it from everyone else. If it isn't deleted in that time, it comes back.
- **After you've polled a message 5 times, it moves to the `-dead` queue.** SQS assumes that whoever is reading it keeps failing. That's the dead-letter queue doing its job, not an error.
- **Only adding a task sends a message.** Moving a task or deleting it doesn't.

After Test 4, a function reads this queue automatically, so the queue is usually empty. You'll look at that function's logs instead.

### 3.10 Where to find a queue's URL and ARN (only if you need them)

You don't need either one for this test. These are the two ways AWS names a queue:
- **The URL** is the address programs use to send and receive messages. It looks like `https://sqs.ap-southeast-2.amazonaws.com/<your account number>/<queue name>`.
- **The ARN** is the name AWS permissions use. It looks like `arn:aws:sqs:ap-southeast-2:<your account number>:<queue name>`.

You can see them in three places:

**On the queue's page in the SQS console.** The **Details** box shows both, each with a copy button. The **Dead-letter queue** tab on the same page shows that the queue is linked to its `-dead` queue after 5 receives.

**In Parameter Store**, where you see the exact value the backend received:
1. In the AWS console, open **Systems Manager**.
2. In its left menu, click **Parameter Store**.
3. Type `SQS_QUEUE_URL` in the search box, and click the parameter `/sdlcforge/taskboard-767fbab00b-dev/backend/SQS_QUEUE_URL`.
4. Click **Show decrypted value** to see the address.

`S3_BUCKET` and `DATABASE_URL` are stored next to it. The deploy keeps every variable of the backend there.

**In CloudShell**, with this command:
```bash
aws sqs list-queues --queue-name-prefix taskboard-767fbab00b-dev
```

### 3.11 If something doesn't work

| What you see | What to do |
|---|---|
| The header says **S3 export off** or **SQS events off**, even after the deploy succeeded and you reloaded the page | The connection from 3.4 wasn't part of the deploy. You can tell from Step 3: `S3_BUCKET` or `SQS_QUEUE_URL` still says **• Not set** instead of **✓ from … on AWS**. Open Step 2 and check that **files** and **task-events** are ticked on the backend card. Then click **⚙ Generate again**, push the infra row, and deploy again. |
| Step 2 doesn't list `files` or `task-events` at all | The web UI change wasn't loaded. Check you clicked **Save configuration** in the web UI. Then click **↻ Sync from web UI** in the Deploy tab. |
| The deploy fails with `AccessDenied`, or with "not authorized to perform", followed by `s3:` or `sqs:` | The deploy user doesn't have the new permissions yet. Do 3.6 with the newly generated `setup.sh`, then deploy again. |
| The **Export to S3** button is grey and can't be clicked | S3 export is off. See the first row. |
| Clicking **Export to S3** shows an error that starts with `500` | Read the backend's log. In the AWS console, open **CloudWatch**, click **Log groups** in the left menu, open `/sdlcforge/taskboard-767fbab00b-dev/backend`, then click the newest log stream. The Python error is near the end. |
| The task is added, but no message arrives in the queue | In the same backend log, search for `Could not send the task.created event to SQS`. The lines under it say why the message wasn't sent. The task itself is saved either way. |

---

## Test 4 – Lambda functions

### 4.1 What this test does

A **Lambda function** is a small piece of code that AWS runs by itself when something happens. It's separate from the backend web app. The thing that starts it is called its **trigger**.

You'll create four functions, each with a different trigger:

| Name | Language | It runs when… | What you'll see it do |
|---|---|---|---|
| `export-watcher` | Python | a file is saved in the `files` bucket, in the `exports/` folder | write the file's name in its log, each time you export |
| `task-worker` | Python | a message arrives in the `task-events` queue | read each "task created" message and write it in its log |
| `heartbeat` | JavaScript | every 5 minutes | write a line in its log each time |
| `hello` | Python | someone opens `/fn/hello` on your app's address | answer with a short JSON greeting |

Where the functions are kept:
- Each function's code goes in the `taskboard` folder, in `functions/<name>/`.
- All their settings go in one file: `.sdlcforge/functions.json`.
- You commit and push both like any other code.

You need Test 3 done first: two of these functions use its bucket and its queue.

### 4.2 Create the four functions

To create a function:
1. In the Deploy tab, open Step 1 (click the circle **1 Source code**).
2. Below the repository row, click **Create a Lambda function**.
3. VS Code asks four or five questions, one after the other, in a box at the top of the window. Type an answer and press Enter, or click a choice in the list.

Do this four times, once per function, and answer the questions as follows.

**export-watcher**
1. When it asks for a function name, type `export-watcher`.
2. When it asks for the language, choose **Python**.
3. When it asks what starts it, choose **A file uploaded to S3**. It uses the bucket `files` without asking, because it's the only bucket.
4. When it asks which folder, it suggests `uploads/`. Delete that, type `exports/`, and press Enter.

**task-worker**
1. Type the name `task-worker`.
2. Choose **Python**.
3. Choose **An SQS queue message**. It uses the queue `task-events` without asking.

**heartbeat**
1. Type the name `heartbeat`.
2. Choose **JavaScript**.
3. Choose **A schedule**.
4. When it shows `rate(1 hour)`, delete that, type `rate(5 minutes)`, and press Enter.

**hello**
1. Type the name `hello`.
2. Choose **Python**.
3. Choose **An HTTP request**.
4. When it asks for the method, choose **GET**.
5. When it shows the path `/hello`, delete that, type `/fn/hello`, and press Enter.

After each function, VS Code opens its code file and shows a message that it was created.

When all four are done, the `taskboard` folder contains:
```
.sdlcforge/functions.json        the settings of all four functions
functions/export-watcher/        lambda_function.py (the code), events/s3.json (a sample event), README.md
functions/task-worker/           lambda_function.py, events/sqs.json, README.md
functions/heartbeat/             index.js, events/schedule.json, README.md
functions/hello/                 lambda_function.py, events/http.json, README.md
```

Step 1 now shows a card for each function, with three buttons: **Test locally**, **Settings** and **Deploy**.

### 4.3 Test each one on your computer

This part runs only on your computer. Nothing in AWS is touched.

1. Start Docker Desktop, if it isn't running.
2. On a function's card in Step 1, click **Test locally**.
   - VS Code runs the function inside AWS's own Lambda container, the same one AWS uses.
   - It gives the function the sample event from its `events` folder.
   - The first test of each language downloads that container, which takes a minute or two.
3. An output panel called **SDLCForge: functions** opens at the bottom of VS Code. It shows what the function printed, and then what it returned.

Check that each function shows the following:

| Function | What the output panel shows |
|---|---|
| `export-watcher` | `New file: s3://files-bucket/exports/example.json (1024 bytes)`, then `{"ok": true}` |
| `task-worker` | `Processing message …: {'orderId': 42}`, then `{"batchItemFailures": []}`. The empty list means no message failed. |
| `heartbeat` | `Scheduled run at …`, then `{"ok":true}` |
| `hello` | a result with `"statusCode": 200`, and `"message": "Hello, world"` in its body |

To try a different input, edit the JSON file in the function's `events` folder, then click **Test locally** again.

### 4.4 Deploy the functions

1. **Commit the new files.**
   1. In VS Code, open **Source Control**: the branch icon in the left-hand bar.
   2. Under **Changes**, you see `functions/…` and `.sdlcforge/functions.json`.
   3. Type a message such as `Add test functions` in the box at the top, and click **Commit**. If VS Code asks whether to stage all your changes, click **Yes**.
2. **Push them.** In the Deploy tab's Step 1, the `taskboard` row now says *1 commit to push*. Click **Push 1 commit**, and wait until the row says **Synced**.
3. **Generate and push the infrastructure.**
   1. Open Step 2 and scroll to the bottom. Click **⚙ Generate again**.
   2. Click **Push 1 commit** on the infra row that appears under the button, and wait until it says **Synced**.

   This adds the four functions, their triggers, and the address `/fn/hello` on your app's URL.
4. **Update the AWS permissions,** exactly as in 3.6: in CloudShell, delete the old `setup.sh`, upload the new one, and run it. Lambda and the scheduler need permissions the deploy user doesn't have yet.
5. **Deploy.** Open Step 4, check the environment is **dev**, and click **🚀 Deploy**. Wait 10 to 20 minutes, until it says **Succeeded**.

### 4.5 Check each one

After the deploy, each function's card in Step 1 shows **version 1**, and three more buttons: **Invoke**, **Logs** and **Roll back**.

**How to read a function's log:**
1. Click **Logs** on its card. The function's log page opens in your browser (in AWS CloudWatch).
2. Click the first log stream in the list, which is the newest one.
3. A new run can take 10 to 30 seconds to appear. Click the refresh button on that page if you don't see it yet.

Now check the four functions:

**export-watcher**
1. In the app, click **Export to S3**.
2. Open export-watcher's log. It has a line starting with `New file: s3://`, followed by the name of the file you just exported.

**task-worker**
1. In the app, add a task.
2. Open task-worker's log. It has a line starting with `Processing message`, followed by the "task created" message.
3. In the SQS console, the task-events queue now stays at 0 messages available, because task-worker takes each message as soon as it arrives.
4. Messages left in the queue from Test 3 were processed right after the deploy, so they appear in the log too.

**heartbeat**
1. Wait 5 to 10 minutes.
2. Open heartbeat's log. There's a line starting with `Scheduled run at` every 5 minutes.

**hello**
1. In your browser, open your app's address followed by `/fn/hello?name=taskboard`.
2. The page shows `{"message": "Hello, taskboard", "method": "GET", "path": "/fn/hello", "received": null}`.

**Try the Invoke button.** Invoke runs a deployed function once, with an input you choose, without its trigger.
1. Click **Invoke** on the **hello** card.
2. A box opens at the top of VS Code with the sample event, in JSON. Press Enter to send it as it is.
3. This starts a short run on GitHub, about a minute long.
4. When it finishes, the run box in Step 4 shows what the function returned.

### 4.6 Roll back one function

1. Open `functions/hello/lambda_function.py`. Change the text `"Hello, %s"` to `"Hi there, %s"`, and save the file.
2. Commit the change in Source Control. Then push it with **Push 1 commit** on the `taskboard` row in Step 1.
3. Open Step 4 and click **🚀 Deploy**. You don't need Generate this time, because only the code changed.
4. When the deploy has succeeded, open your app's address followed by `/fn/hello`. It now says **Hi there, world**, and the hello card in Step 1 shows **version 2**.
5. On the hello card, click **Roll back**.
6. In the list that opens at the top of VS Code, choose **Version 1**. In the confirmation, click **Roll back**.
7. A short run starts, about a minute long. When it's finished, `/fn/hello` says **Hello, world** again.
   - Nothing was rebuilt: AWS keeps every version of the function.
   - Roll back only told AWS to use version 1 again.
8. The next time you deploy, your latest code goes live again, as version 3.

### 4.7 Failed events

**What this tests.** When a function started by a file upload or a schedule fails, AWS retries it twice. If it still fails, AWS doesn't throw the event away: it keeps it in a separate queue for that function, the **failed-events queue**, for 14 days. You can look at it there later.

(`task-worker` is different. A message it fails on goes back into `task-events`. After 5 tries, it moves to the `-dead` queue from Test 3.)

1. **Make export-watcher fail.**
   1. Open `functions/export-watcher/lambda_function.py`.
   2. Right under the line `def handler(event, context):`, add a new line: `raise Exception("test failure")`. Indent it like the line below it, with four spaces.
   3. Save the file. The start of the function now looks like this:
      ```python
      def handler(event, context):
          raise Exception("test failure")
          for record in event["Records"]:
      ```
2. Commit and push the change as in 4.6, then deploy from Step 4.
3. **Trigger the failure.** When the deploy has succeeded, click **Export to S3** in the app.
   - The export itself still works, and the file is saved in S3.
   - Only export-watcher, which reacts to the new file, fails.
4. **Watch it fail.** Open export-watcher's log. Over about 3 minutes, `Exception: test failure` appears three times: the first try, then two retries. After that, AWS stops trying.
5. **Find the kept event.** There are two ways; use either one.
   - **In the Deploy tab:** the card only updates its count when you deploy. So deploy once more from Step 4. The export-watcher card then says that 1 failed event is kept in its failed-events queue.
   - **In the SQS console:**
     1. Search for `taskboard-767fbab00b-dev`. You now see two more queues besides task-events and its `-dead` queue: the failed-events queues of export-watcher and heartbeat.
     2. The one with **1** under **Messages available** is export-watcher's. Click it.
     3. Click **Send and receive messages**, then **Poll for messages**, then click the message.
     4. Its body contains the original event and the error.
6. **Undo it.** Delete the `raise` line, save, commit, push, and deploy again.

### 4.8 Make heartbeat run less often

Running every 5 minutes is only for this test.
1. On the **heartbeat** card in Step 1, click **Settings**. The file `.sdlcforge/functions.json` opens.
2. In the part about `heartbeat`, change `"rate(5 minutes)"` to `"rate(1 day)"`, and save the file.
3. Commit and push it as in 4.6.
4. Open Step 2, click **⚙ Generate again**, then click **Push 1 commit** on the infra row. A schedule is part of the infrastructure, so this time Generate is needed.
5. Deploy from Step 4.

---

## Test 5 – Backups and recovery

**What this tests:**
- You can back up the database whenever you want.
- You can restore a backup as a separate, new database, without touching the live one.

### 5.1 Take a backup

1. In the Deploy tab, open Step 4 and click **Back up data**. A run starts. It takes 3 to 10 minutes, because it waits until AWS has finished the backup.
2. When it says **Succeeded**, the run box shows the result:
   - **For `app-db`:** an address that starts with `arn:aws:rds:`, like `arn:aws:rds:ap-southeast-2:123456789012:snapshot:taskboard-767fbab00b-dev-1a2b3c4d`. This is the backup's ARN. **Select it and copy it**; you'll need it in 5.3.
   - **For `files`:** a note instead of an ARN. The bucket already keeps every version of every file, so it doesn't need a separate backup.

You can also find the backup in the AWS console:
1. Open **RDS**.
2. Click **Snapshots** in the left menu, then the **Manual** tab.
3. Click the snapshot. Its ARN is shown in its details.

The other snapshots in that list were made automatically, by each deploy, just before it updated the database.

### 5.2 Change the live data

In the app, delete one task, and remember which one. The backup still has it, and the live database doesn't. That's how you'll tell the two apart.

### 5.3 Restore the backup as a new database

1. In Step 4, click **Recover data**.
2. A list opens at the top of VS Code. Choose **app-db**. Only databases are listed, because the bucket and the queue aren't restored this way.
3. Paste the ARN you copied in 5.1, and press Enter.
4. A run starts. It creates a **new** database, named `taskboard-767fbab00b-restore-` followed by a code. This takes 10 to 20 minutes.
5. **Check:**
   - In the AWS console, open **RDS** and click **Databases**. Both databases are listed: the live one (`taskboard-767fbab00b-dev-…`) and the restored one.
   - The app still shows your latest tasks, still without the one you deleted. The live database wasn't touched.

A restore never replaces live data. After a real accident, you would first look at the restored copy. Then you would switch the app over to it, by adding it in the web UI as an **Existing** service and connecting the backend to it. You don't need to do that for this test.

### 5.4 Delete the restored database

A restored database costs as much as the live one, so delete it now. AWS creates it with **deletion protection** on, so you switch that off first.

1. In **RDS**, on the **Databases** page, click the circle next to the database whose name contains `restore`. Make sure it's not the `-dev-` one.
2. Click **Modify**.
3. Find **Deletion protection** and untick **Enable deletion protection**.
4. Click **Continue** at the bottom.
5. Choose **Apply immediately**, then click **Modify DB instance**.
6. Wait until the database's status is **Available** again. This takes about a minute.
7. With the same database selected, open the **Actions** menu and choose **Delete**.
8. In the window that opens:
   1. untick **Create final snapshot**;
   2. untick **Retain automated backups**;
   3. tick the box that says you understand;
   4. type `delete me` and click **Delete**.

Keep the backup from 5.1 for now. Test 9 deletes the backups.

---

## Test 6 – A failing deploy on Lambda

**What this tests:** if a new version of the backend fails its health check, the deploy stops and reports it.

The app has a switch to make this happen: when the variable `HEALTH_FAIL` is `true`, the address `/api/health` returns an error.

This test is for Lambda. You did the Fargate version in Test 7.5.

### 6.1 Switch back to Lambda

Skip this section if the app's header already says **AWS Lambda**.

1. In the web UI's Deployment stage, find **Backend compute** and choose **AWS Lambda + API Gateway**. Click **Save configuration**.
2. In VS Code's Deploy tab, click **↻ Sync from web UI**.
3. Open Step 2. The Lambda settings are back near the top. Check these values:

   | Setting | Value |
   |---|---|
   | Web app memory | `512` |
   | Web request timeout | `30` |
   | Web app maximum concurrency | `10` |
   | Container health path | `/api/health` |

4. At the bottom of Step 2:
   1. Click **⚙ Generate again**.
   2. Click **Push 1 commit** on the infra row.
5. Update the AWS permissions as in 3.6: in CloudShell, delete the old `setup.sh`, upload the new one, and run it.
6. Deploy from Step 4. It takes 10 to 20 minutes.
   - The Fargate service and its load balancer are removed, and the Lambda backend comes back.
   - Your data, the bucket, the queue and the functions stay as they are.
7. Open the app. The header says **AWS Lambda**, and your tasks are still there.

### 6.2 Turn on the failure switch

1. Open Step 3 in the Deploy tab. Check that the dropdown next to **App variables** says **dev**.
2. Find the row `HEALTH_FAIL`. It says **• Not set**. Click the **Set** button on that row.
3. A box opens at the top of VS Code, asking for its value. Type `true` and press Enter. The box hides what you type, as it does for every secret.
4. The row now has a green badge, and two new buttons: **Change** and **Delete**.
5. The tab sends the value to GitHub by itself. The line at the bottom of Step 3 then says **✓ Synced to GitHub**. If it says *Not on GitHub yet* instead, click **Sync now**.
6. Open Step 4 and click **🚀 Deploy**.

### 6.3 What should happen

- **The run fails**, while it deploys the application. Its message says that *its Lambda web health check failed*.
- **The page itself doesn't change**, because the frontend files aren't published after a failure.
- **Known limitation: the app's data stops loading.** On Lambda, the new version is already live when the check runs, so the app's API stops working.
  - Open your app's address followed by `/api/health`. It shows `{"detail":"HEALTH_FAIL is set"}`.
  - On Fargate, in Test 7.5, the old version kept working instead.
- **Step 4 records the failure.** The line under its buttons says the release's deploy failed.

### 6.4 Recover

1. **Remove the switch first**, or the next deploy fails again.
   1. In Step 3, find the row `HEALTH_FAIL` and click its **Delete** button. The button is there now, because the variable has a value.
   2. In the confirmation, click **Delete**.
   3. The row goes back to **• Not set**. It stays in the list, because the code reads it, and that's fine.
   4. Wait for **✓ Synced to GitHub** at the bottom.
2. **Roll back.** In Step 4, click **Roll back release**.
   1. A list of earlier releases opens at the top of VS Code, showing only releases that deployed successfully, newest first. Choose the top one.
   2. In the confirmation, click **Roll back**.
3. When the run finishes, the app works again. Lambda keeps each version together with its variables, so the old version doesn't have `HEALTH_FAIL`.

Instead of rolling back, you could also simply deploy again, now that `HEALTH_FAIL` is gone.

Please write down what the run and the app showed. See the request at the end of this guide.

---

## Test 7 – ECS on Fargate

**What this tests:** the same app on **ECS on Fargate** instead of Lambda.
- On Fargate, the backend runs as a container that's always on, behind a **load balancer**.
- The data, the functions and the services stay as they are.

### 7.1 Choose Fargate in the web UI

1. In the web UI's Deployment stage, find **Backend compute** and choose **Amazon ECS on Fargate**.
2. Click **Save configuration**.
3. In VS Code's Deploy tab, click **↻ Sync from web UI**.

### 7.2 Set the container's size (Step 2)

Open Step 2. The Fargate settings are near the top. Set these values:

| Setting | Value |
|---|---|
| Task CPU units | `256` |
| Task memory (MB) | `512` |
| Minimum tasks | `1` |
| Maximum tasks | `2` |
| Container health path | `/api/health` |

### 7.3 Generate, give permissions, deploy

1. At the bottom of Step 2:
   1. Click **⚙ Generate again**.
   2. Click **Push 1 commit** on the infra row, and wait for **Synced**.
2. Update the AWS permissions as in 3.6: in CloudShell, delete the old `setup.sh`, upload the new one, and run it. Fargate and the load balancer need new permissions.
3. Deploy from Step 4. It takes 10 to 20 minutes.
   - The Lambda backend is removed.
   - An ECS service, a load balancer and one Fargate container are created.

### 7.4 Check

1. **The app.** Open it. The header says **ECS on Fargate**, and your tasks are still there.
2. **The service.** In the AWS console:
   1. Open **ECS** and click **Clusters**.
   2. Click the cluster `taskboard-767fbab00b-dev`.
   3. On the **Services** tab, the service shows **1** running task.
3. **The target.** In the AWS console:
   1. Open **EC2** and click **Target groups** in the left menu.
   2. Click the backend's target group, then its **Targets** tab.
   3. The target's health status is **healthy**.
4. **The load balancer.** Still in EC2, click **Load balancers** in the left menu. There's one, and its state is **Active**.
5. **The logs.** In **CloudWatch**, open the log group `/sdlcforge/taskboard-767fbab00b-dev/backend`. It now has the container's logs.
6. **The functions.** If you've done Test 4, the functions still work, because they stay on Lambda.

### 7.5 A failing deploy on Fargate

1. **Turn on the failure switch.** Open Step 3, and make sure the dropdown next to **App variables** says **dev**. Then:
   1. Find the row `HEALTH_FAIL`, which says **• Not set**, and click its **Set** button.
   2. Type `true` in the box at the top of VS Code, and press Enter.
   3. Wait until the bottom line says **✓ Synced to GitHub**.
2. **Deploy** from Step 4.
3. **What should happen:**
   1. ECS starts a new container, and it fails its health checks.
   2. ECS's safety switch, called the *circuit breaker*, stops the update.
   3. **The old container keeps serving**, so the app keeps working the whole time.
4. **Please write down whether the run says Failed.** This is the one case that hasn't been tested on real AWS yet.
5. **Turn the switch off.**
   1. In Step 3, click **Delete** on the `HEALTH_FAIL` row, and confirm with **Delete**. The row goes back to **• Not set**.
   2. Wait for **✓ Synced to GitHub**.
   3. Deploy again from Step 4.

### 7.6 Optional: two containers

1. In Step 2, set **Minimum tasks** to `2`.
2. Click **⚙ Generate again**, then click **Push 1 commit** on the infra row.
3. Deploy from Step 4.
4. ECS now runs two containers, in two different data centres (*availability zones*).

To go back to Lambda later, follow 6.1.

---

## Test 8 – Custom domain (optional)

Skip this test if you don't have a domain where you can add DNS records.

**What this tests:** the app opening on your own address with a valid HTTPS certificate, such as `https://dev.app.example.com`, instead of on CloudFront's address, such as `https://d1a2b3c4.cloudfront.net`.

**Some background first:**
- **DNS** is what turns a name like `dev.app.example.com` into an address. Your domain's DNS is managed by the company you bought it from, or wherever you moved it to (Cloudflare, Hostinger, Route 53…).
- **Route 53** is AWS's own DNS service. A **hosted zone** is the list of DNS records that Route 53 keeps for one domain or subdomain.
- **ACM** (AWS Certificate Manager) gives out free HTTPS certificates. CloudFront only uses certificates from the **US East (N. Virginia)** region. That's true even though your app runs in Sydney.
- **Which address each environment gets:**
  - `prod` gets the domain itself, `app.example.com`;
  - `dev` gets `dev.app.example.com`.

In the steps below, replace `app.example.com` with a subdomain of a domain you own, for example `taskboard.yourdomain.com`.

**The domain is entered in the web UI,** not in VS Code. The **Domain** field in Step 2 is locked and just shows what the web UI says.

Pick **one** of the two ways below.

### Way A – let AWS manage the subdomain (the deploy does the DNS for you)

1. **Create a hosted zone.**
   1. In the AWS console, open **Route 53**, click **Hosted zones** in the left menu, and click **Create hosted zone**.
   2. In **Domain name**, type `app.example.com`. Leave **Type** on **Public hosted zone**, and click **Create hosted zone**.
   3. The new zone's page opens. Write down its **Hosted zone ID**, which starts with `Z`.
   4. Also write down the 4 values of its record of type **NS**. They look like `ns-123.awsdns-45.com`.

   A hosted zone costs about US$0.50 a month.
2. **Hand the subdomain over to AWS.** Go to wherever your domain's DNS is managed now (Cloudflare, Hostinger…). Add 4 records of type **NS**, each with the name `app`, one for each of the 4 values from step 1.
3. **Check the hand-over.** It can take from a few minutes to an hour. Run this in a terminal:
   ```bash
   nslookup -type=NS app.example.com
   ```
   It works when the answer lists the four `awsdns` servers.
4. **Enter the domain in the web UI.**
   1. In the web UI's Deployment stage, type `app.example.com` in the **Domain** field and click **Save configuration**.
   2. In the Deploy tab, click **↻ Sync from web UI**.
5. **Enter the hosted zone in Step 2.**
   1. Open Step 2 and click **Network and domain settings** to expand that section.
   2. Paste the `Z…` ID into **Route 53 hosted zone id**.
   3. Leave **Issued ACM certificate ARN** empty.
6. **Generate, give permissions, deploy.**
   1. Click **⚙ Generate again**, then click **Push 1 commit** on the infra row.
   2. Update the AWS permissions as in 3.6.
   3. Deploy from Step 4.
7. **The deploy does the rest:**
   1. it asks ACM for a certificate for `dev.app.example.com`;
   2. it proves to ACM that the name is yours, by adding a record to the hosted zone;
   3. it waits for the certificate, usually 2 to 10 minutes;
   4. it attaches the certificate to CloudFront;
   5. it adds a DNS record that points `dev.app.example.com` at CloudFront.
8. **Check:**
   1. Open `https://dev.app.example.com`. It shows the app.
   2. In the AWS console, switch the region to **US East (N. Virginia)** and open **Certificate Manager**. The certificate's status is **Issued**.

### Way B – keep your DNS at Cloudflare or Hostinger (you add the records yourself)

1. **Ask for a certificate.**
   1. In the AWS console, switch the region (top right) to **US East (N. Virginia)**.
   2. Open **Certificate Manager** and click **Request**. Leave **Request a public certificate** selected and click **Next**.
   3. In **Fully qualified domain name**, type `app.example.com`.
   4. Click **Add another name to this certificate** and type `*.app.example.com`. This also covers `dev.app.example.com`.
   5. Leave **Validation method** on **DNS validation**, and click **Request**.
2. **Prove the domain is yours.**
   1. Open the new certificate. In its **Domains** section, it shows a **CNAME name** and a **CNAME value**.
   2. At your DNS provider, add a record of type **CNAME** with that name and that value. On Cloudflare, set the record to **DNS only** (the grey cloud, not the orange one).
   3. Wait until the certificate's status says **Issued**. This takes from a few minutes to an hour.
   4. Keep that record afterwards. ACM uses it to renew the certificate every year.
3. **Copy the certificate's ARN.** It's on the certificate's page and starts with `arn:aws:acm:us-east-1:`.
4. **Enter the domain in the web UI.**
   1. In the web UI's Deployment stage, type `app.example.com` in the **Domain** field and click **Save configuration**.
   2. In the Deploy tab, click **↻ Sync from web UI**.
5. **Enter the certificate in Step 2.**
   1. Open Step 2 and click **Network and domain settings** to expand that section.
   2. Paste the ARN into **Issued ACM certificate ARN**.
   3. Leave **Route 53 hosted zone id** empty.
6. **Generate, give permissions, deploy.**
   1. Click **⚙ Generate again**, then click **Push 1 commit** on the infra row.
   2. Update the AWS permissions as in 3.6.
   3. Deploy from Step 4.
7. **Point your address at CloudFront.** The Deploy tab doesn't show CloudFront's own address yet, so take it from the console:
   1. In the AWS console, open **CloudFront**.
   2. In the list of distributions, find the one whose **Alternate domain names** shows `dev.app.example.com`. Copy its **Domain name**, which looks like `d1a2b3c4.cloudfront.net`.
   3. At your DNS provider, add a record of type **CNAME**: name `dev.app`, value `d1a2b3c4.cloudfront.net`. On Cloudflare, set it to **DNS only**.
8. **Check:** open `https://dev.app.example.com`. It shows the app. A new DNS record can take a few minutes to start working.

### Checking any domain

Run these in a terminal.

To check that the name points somewhere:
```bash
nslookup dev.app.example.com
```

To check that the site answers over HTTPS:
```bash
curl -sI https://dev.app.example.com
```

To check the certificate's names, issuer and expiry date:
```bash
openssl s_client -connect dev.app.example.com:443 -servername dev.app.example.com </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

---

## Test 9 – Remove compute and clean up

There are two different buttons in Step 4:
- **Remove compute** turns off everything that runs the app or sends visitors to it, but **keeps your data**. A later deploy brings the app back, with the same tasks.
- **Delete everything…** deletes everything the project has in AWS, in every environment, **including the data**. It can't be undone.

### 9.1 Remove compute (the data stays)

1. In Step 4, click **Remove compute**. In the confirmation, click **Remove compute**.
2. Wait 10 to 30 minutes. CloudFront in particular is slow to remove.
3. **Check what's gone:**
   - the app's address no longer opens;
   - the backend (the Lambda web app, or the Fargate service and its load balancer);
   - the functions, API Gateway and CloudFront;
   - the NAT gateways.
4. **Check what's kept:**
   - the database `app-db`, which RDS still shows as **Available**;
   - the `files` bucket, with its `exports` folder;
   - the SQS queues;
   - the image repositories, the logs and the IAM roles.

   Step 4 now says that compute is removed and the data is kept.

The database still costs money while it exists.

If you like, deploy once more: everything comes back on top of the same data, and your tasks are still there. Then continue with 9.2.

### 9.2 Delete everything (when you've finished all the tests)

1. **If deletion protection is on for `app-db`, turn it off first.** It's on by default, but in your plan it's already off (step 1.3). To check, or to turn it off:
   1. In **RDS**, select the database and click **Modify**.
   2. Untick **Enable deletion protection** and click **Continue**.
   3. Choose **Apply immediately** and click **Modify DB instance**.
2. In Step 4, click **Delete everything…**. A warning lists everything that will be deleted. Click **Continue…**.
3. A box at the top of VS Code asks you to type the project's name. Type `taskboard-test` and press Enter.
4. A run starts. It takes 20 to 40 minutes, and deletes, in every environment:
   - the backend, the functions, CloudFront, API Gateway and the load balancer;
   - the database and all its data;
   - the `files` bucket and its files;
   - the queues, secrets and parameters;
   - the image repositories, logs, IAM roles and network;
   - every database backup;
   - the Terraform state.
5. **What stays:**
   - your code and its GitHub repositories;
   - the `infra` repository;
   - the GitHub secrets;
   - the IAM policies, which 9.3 removes.
6. When the run has finished, click **View the run on GitHub** and read the end of the log. If it couldn't delete something, it's listed there in a line starting with `Left:`, with the reason.

### 9.3 Remove the IAM policies

The deploy user isn't allowed to delete its own permissions, so an administrator does this, after Delete everything has finished.

1. Sign in to the AWS console as an administrator and open CloudShell.
2. Open the **Actions** menu and choose **Upload file**. Choose `C:\Users\AnukulParajuli\codes\taskboard\infra\iam\remove.sh` and click **Upload**.
3. Type `bash remove.sh` and press Enter. It detaches and deletes the policies `taskboard-767fbab00b-deploy-1`, `-2` and so on, and `taskboard-767fbab00b-runtime-boundary`.
   - If AWS refuses to delete the boundary because a role still uses it, Delete everything hasn't finished yet. Wait, then run the command again.
4. The deploy user and its access keys stay. Delete them in IAM if no other project uses them.

### 9.4 Check that nothing is left

In the AWS console, in the Sydney region, search for `taskboard-767fbab00b` on each of these pages:
- **RDS**, on the **Databases** page and on the **Snapshots** page: nothing of yours.
- **VPC**, on the **NAT gateways** page: nothing of yours, or only gateways whose state is **Deleted**.
- **S3**: no buckets starting with your namespace.
  - A bucket called `sdlcforge-tfstate-<account>-ap-southeast-2` may remain. It's shared by every project in this AWS account, and costs almost nothing.
- **SQS**: no queues starting with your namespace.

The next day, open **Billing** and check that the daily charges have stopped.

### 9.5 Cleaning up by hand (only if Delete everything can't run)

These are the things Remove compute keeps. Delete them in the AWS console:

1. **The database.** In RDS, turn off deletion protection as in 9.2, then select the database and choose **Delete** from the **Actions** menu, without a final snapshot.
2. **The backups.** In RDS, click **Snapshots**, open the **Manual** tab, and delete the backups made by the deploys and by Test 5. You pay for their storage.
3. **The bucket.**
   1. In S3, select the `files` bucket and click **Empty**. This also removes every old version.
   2. Then select it again and click **Delete**.
4. **The queues.** In SQS, delete every queue whose name starts with your namespace. These are task-events, its `-dead` queue, and the functions' failed-events queues.
5. **The database password.** In **Secrets Manager**, delete the secret `/sdlcforge/taskboard-767fbab00b-dev/app-db`.
6. **The parameters.** In **Systems Manager**, open **Parameter Store**, and delete the parameters whose names start with `/sdlcforge/taskboard-767fbab00b-dev/`.
7. **Optional, because they cost nothing:**
   - the image repositories in **ECR**;
   - the log groups in **CloudWatch**;
   - the IAM roles whose names start with `taskboard-767fbab00b-dev`;
   - the VPC. It's free once its NAT gateways are gone.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| "The IAM permissions boundary … does not exist" | Do step 1.5. |
| "AccessDenied" or "not authorized to perform" during a deploy | Generate added something new. Run the newly generated `setup.sh` in CloudShell, as in 3.6, then deploy again. |
| "generate a database password in the Secrets step" | Open Step 3, click **Generate** next to `APP_DB_PASSWORD`, and wait for **✓ Synced to GitHub**. |
| The header says **database: unavailable** | Either `DATABASE_URL` was typed in Step 3 (delete it there), or the backend isn't connected to `app-db` in Step 2 (tick it). |
| The header says **S3 export off** or **SQS events off** | The bucket or the queue isn't connected to the backend. See 3.11. |
| "its Lambda web health check failed" | `/api/health` didn't answer. Check three things: that Step 2's **Container health path** is `/api/health`; that `HEALTH_FAIL` says **• Not set** in Step 3; and the backend's log in CloudWatch. |
| "Migration failed" | In CloudWatch, open the backend's log group and the log stream for the migration. The new version wasn't started. |
| "Lambda environment exceeds 4096 bytes" | A Lambda can only take 4 KB of variables. Make them shorter or fewer, or keep large values in Secrets Manager. |
| The Fargate target is **unhealthy** | Either the health path is wrong, or the app isn't listening on the port in `$PORT`. |
| The page loads, but its data doesn't, and CloudFront answers 403 or 404 | Either the deploy didn't finish, or the backend's **URL path** in Step 2 isn't `/api`. |
| **Test locally** fails straight away | Docker Desktop isn't running. Also, the first test of each language downloads AWS's container, which takes a minute or two. |
| A function's card has no **Invoke**, **Logs** or **Roll back** buttons | It isn't deployed yet. Follow 4.4: commit and push, Generate, run `setup.sh`, and deploy. |
| `/fn/hello` shows the Taskboard page instead of JSON | The address `/fn/hello` doesn't exist yet, because Generate wasn't run after you created `hello`. Click **⚙ Generate again** in Step 2, push the infra row, and deploy. |
| Messages disappear from `task-events` without being deleted | Either they were polled 5 times and moved to the `-dead` queue (see 3.9), or `task-worker` from Test 4 read them. |

Please tell me what you saw in Test 6 and Test 7.5 (the failing deploys), and anything that doesn't match this guide.

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
