# FORMA Cloud Sync setup (Firebase Spark)

FORMA Cloud Sync uses Firebase Authentication (Google sign-in) and Cloud Firestore. GitHub Pages remains the static website host. The Firebase web configuration is public; **Firestore Security Rules are what protect the records**.

## 1. Create a Firebase project

1. Open https://console.firebase.google.com/ and create a project named `FORMA`.
2. Keep the project on the **Spark (no-cost)** plan. Do not add a billing account or upgrade the project.
3. In Project settings, add a Web App named `FORMA Web`.
4. Copy the web app configuration shown by Firebase.

## 2. Enable Google sign-in

1. Open **Authentication → Sign-in method** (or **Sign-in providers**, depending on the Console layout).
2. Enable **Google** and save.
3. Open **Authentication → Settings → Authorized domains**.
4. Add `prottoynishan11.github.io`. Keep `localhost` for local development if it is listed.

## 3. Create Cloud Firestore

1. Open **Firestore Database → Create database**.
2. Create the database in production mode.
3. Choose a region near Bangladesh, such as `asia-south1` if it is available in your project. The location cannot be changed after creation.
4. Open the **Rules** tab and replace the rules with the full contents of `firestore.rules` in this repository. Publish the rules.

The rules allow a signed-in person to access only `users/{their-own-UID}/items`. Do not replace them with public rules such as `allow read, write: if true`.

## 4. Add your Firebase web configuration

1. Open `js/firebase-config.js` in the FORMA GitHub repository.
2. Replace the four placeholder values with the exact values from **Project settings → Your apps → FORMA Web → SDK setup and configuration**.
3. Commit the file to `main`.

The web config contains public identifiers, not passwords. Never paste a service-account JSON file, private key, Admin SDK credential, or Google account password into GitHub or this chat.

## 5. First laptop sync

1. Open https://prottoynishan11.github.io/forma/ .
2. Open **Settings & backup → Cloud sync**.
3. Select **Continue with Google** and sign in with the Google account you intend to use on both devices.
4. Keep the page open until the status reads **Synced**. FORMA merges existing local records with cloud records. Records with the same ID are reconciled per record; newer timestamped local session/weigh-in edits can be kept, while the cloud version wins when no reliable timestamp exists.
5. Check your workouts, routines, exercises, body-weight history and settings.

## 6. Connect your iPhone

1. Open the same FORMA website in Safari.
2. Sign in using the same Google account.
3. Wait for **Synced**. New changes should appear on the other signed-in device while it is online.

## How synchronization works

- Workouts, exercises, routines, weigh-ins, settings and the current draft are stored as separate documents under your Firebase user ID.
- Firestore listeners deliver changes to the other signed-in device.
- Firestore's web persistent cache keeps data available offline on supported browsers, then uploads queued writes after reconnection.
- Simultaneous edits to the exact same record use a last-write-wins approach. FORMA overlays unsynced local edits during reconciliation, but avoid editing the same workout on both devices at the same time.
- Sign out on shared devices. The local browser cache remains on that device; use a personal, trusted device.
- JSON backup/restore remains available as an extra safety copy. Cloud sync is not a replacement for periodic backups.

## Free-plan limits

Firestore Standard's no-cost quota currently includes 1 GiB stored data, 50,000 document reads/day, 20,000 writes/day, 20,000 deletes/day and 10 GiB outbound transfer/month. On Spark, a product quota overage stops that product until the next quota period; it does not automatically charge a card. Check current Firebase billing documentation before setup:
https://firebase.google.com/docs/firestore/quotas
https://firebase.google.com/docs/projects/billing/firebase-pricing-plans

Google sign-in with Firebase Authentication is a no-cost social sign-in provider. Phone/SMS authentication is not used by FORMA.

## Troubleshooting

- **Setup required:** the placeholders in `js/firebase-config.js` have not been replaced.
- **auth/unauthorized-domain:** add `prottoynishan11.github.io` to Firebase Authentication's authorized domains.
- **permission-denied:** check that the published Firestore rules match `firestore.rules`.
- **Offline cache:** reconnect to the internet and keep FORMA open until it shows **Synced**.
- **Account mismatch:** this browser has already been linked to a different Firebase UID. Sign back into that account or use a separate browser profile; this guard prevents accidentally merging two people's local data.
