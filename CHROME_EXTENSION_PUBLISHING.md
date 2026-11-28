# Publishing the Keel MV3 extension to the Chrome Web Store

> **Current delivery uses the free path instead.** The `/keel-in-chrome` CTAs
> download `keel-extension.zip` and show a load-unpacked guide
> (`ui/chrome-install.js`); no store account or fee is required. Google charges
> a one-time $5 Chrome Web Store developer registration fee, and its API cannot
> create the first item, so automated publication could not be completed. This
> runbook remains valid if you later choose to pay and publish. To switch back
> to a one-click store link, set `window.KEEL_INSTALL_MODE = "store"` and put
> the published item URL in `window.KEEL_CHROME_WEB_STORE_URL` in
> `keel/site/ui/chrome-install.js`.

This document is the runbook for turning the packaged extension in this repo
into a live Chrome Web Store item and wiring the real install URL into the
site. **Nothing here has been done yet:** the extension is *packaged*, not
*published*. Do not claim a store URL is live until step 8 below is complete
and the URL resolves in a browser.

## Inputs in this repository

| Thing | Path |
|-------|------|
| Unpacked MV3 extension (source of truth) | `keel/site/extension/` |
| Uploadable ZIP (manifest at root) | `keel/site/keel-extension.zip` |
| Listing copy / metadata to paste into the dashboard | `keel/site/store-assets/store-listing.md` |
| Listing images (when created by the asset agent) | `keel/site/store-assets/` |
| Install-CTA resolver (holds the store URL token) | `keel/site/ui/chrome-install.js` |
| Landing copies that consume the resolver | `keel/site/keel-in-chrome.html` and `keel/site/keel-in-chrome/index.html` |
| Privacy policy deployed with the site | `https://keel-desktop.vercel.app/privacy` (source: `keel/site/privacy.html`) |
| QA gate to re-run after any change | `python verify_keel_chrome.py` |

Before uploading, confirm the ZIP is still byte-identical to the folder. QA
check **4e** does this; equivalently:

```powershell
cd keel/site
python -c "import zipfile,pathlib; p=pathlib.Path('extension'); z=zipfile.ZipFile('keel-extension.zip','w',zipfile.ZIP_DEFLATED); [z.write(f, f.relative_to(p).as_posix()) for f in sorted(p.rglob('*')) if f.is_file()]; z.close()"
```

`manifest.json` must be at the **root** of the archive (not inside an
`extension/` subfolder). Never upload the folder itself.

---

## Step 1 — Prerequisites (one time)

1. A Google account you are willing to make public as the developer.
2. Enrol in the [Chrome Web Store Developer account](https://chromewebstore.google.com/register)
   and accept the developer agreement.
3. Pay the **one-time $5 registration fee** if Google charges it for your
   account/region (it has been waived for some early or promo accounts — the
   dashboard tells you which case applies). This is a real charge to a payment
   method; it is not something an agent can do for you.
4. Decide the developer identity shown on the listing. Use the name in
   `store-listing.md` so the listing and the dashboard agree.
5. For automated uploads only (step 9): a Google Cloud project with the
   Chrome Web Store API enabled and an OAuth client. The manual dashboard
   route needs none of this.

## Step 2 — Fill in the listing draft

Open the [Chrome Web Store Developer Dashboard](https://chromewebstore.google.com/devdashboard)
→ **Add new item** → upload `keel/site/keel-extension.zip`. The dashboard
validates the manifest and unpacks the ZIP; fix any error it reports before
continuing. Then, from `keel/site/store-assets/store-listing.md`, fill in:

- **Item name** and **summary** (short, shown in search results).
- **Full description** (supports limited HTML: paragraphs, `<b>`, `<ul>`/`<li>`,
  `<a href>`; no scripts or inline styles).
- **Category** (e.g. Productivity) and **language**.
- **Developer / support email and site URL**.
- Any **custom steps** or release notes the listing file calls for.

Keep the draft saved; you can edit listing fields after approval without a
new ZIP review (a new ZIP always triggers review).

## Step 3 — Required and recommended assets

Propagate the same visual identity used in the extension package:

| Asset | Requirement | Where to get it |
|-------|-------------|-----------------|
| Extension icon | PNG, at least **128×128** (the package already ships 16/48/128 icons in `extension/icons/`) | `keel/site/extension/icons/icon-128.png` |
| Screenshots | **At least 1** required; up to 5. Use **1280×800** (or 640×400) PNG/JPEG; the store shows them in the listing gallery | `keel/site/store-assets/` (or capture from the running side panel / site) |
| Promotional small tile | **440×280** PNG/JPEG — optional but strongly recommended | `keel/site/store-assets/` |
| Promotional large tile | **920×680** PNG/JPEG — optional | `keel/site/store-assets/` |
| Promo video | Optional; must be a public YouTube URL | per `store-listing.md` |

Screenshots should show the real side panel (chat, sessions, settings), not
the retired store-replica page.

## Step 4 — Privacy policy and data disclosures

1. Set **Privacy policy URL** to `https://keel-desktop.vercel.app/privacy`.
   It must be publicly reachable without a login, and the published
   `privacy.html` must match what the extension actually does.
2. Complete the **Data safety / privacy practices** form: declare what the
   extension stores locally, what (if anything) leaves the device, and the
   purpose. Keel is local-first; state that accurately rather than claiming
   "no data collected" if settings/sessions are stored in `chrome.storage`.
3. If any permissions look broad (e.g. host access), justify them in the
   "Site access" justification field. The review team may reject an
   unjustified host permission.

## Step 5 — Distribution and visibility

- Choose **Visibility** while under review:
  - **Private** — only trusted testers you list can install; safest for a
    first submission.
  - **Unlisted** — anyone with the direct link can install; not searchable.
    Good for a soft launch once approved.
  - **Public (Visible)** — appears in search. Switch to this only after you
    are happy with the approved listing.
- If you use *Private* or *Unlisted*, add tester accounts under **Publish →
  Trusted testers / test accounts** before submitting.
- Confirm the target audience is **not** set to "child-directed" unless that
  is genuinely the case; the extra Families policy review adds time.

## Step 6 — Submit for review and expect a wait

**Publish → Submit for review.** Timeline (not guaranteed):

- Express review (available to eligible registered developers with a clean
  history): often a few hours.
- Standard review: typically **1–5 business days**, occasionally longer for
  new accounts, permission questions, or a rejected listing that needs a
  resubmission.

Watch the dashboard **Status** column and the developer email for the result.
If rejected, read the policy reason, fix the ZIP/listing, upload the new ZIP
and resubmit; QA check 4e must pass again after every regeneration.

## Step 7 — Obtain the item ID and exact store URL

Once approved and published (or unlisted), open the item in the dashboard.
The item ID is the 32-character lowercase `a`–`p` string in the dashboard URL:

```
https://chromewebstore.google.com/devdashboard/<CATEGORY>/<ITEM_ID>/...
```

Its canonical store URL is:

```
https://chromewebstore.google.com/detail/<slug>/<ITEM_ID>
```

`<slug>` is the human-readable part Google derives from the item name (e.g.
`keel-in-chrome`); `<ITEM_ID>` is the authoritative part. Copy both exactly
from the browser address bar of the public listing — do not invent or guess
an ID. Verify the URL opens the Keel listing before wiring it into the site.

## Step 8 — Substitute the ID into the site and redeploy

1. Open `keel/site/ui/chrome-install.js`. It is the single source of truth:

   ```js
   window.KEEL_CHROME_WEB_STORE_URL =
     "https://chromewebstore.google.com/detail/keel/PENDING_ITEM_ID";
   ```

   Replace only `PENDING_ITEM_ID` with the exact 32-character ID from step 7.
   Do **not** hard-code the ID in individual HTML buttons: every
   `[data-store-install]` element is rewritten by the script at load time.
2. Confirm **each** `Add to Chrome` CTA in *both* landing copies —
   `keel/site/keel-in-chrome.html` and `keel/site/keel-in-chrome/index.html` —
   carries `data-store-install` and resolves to that same URL (the placeholder
   `href` is acceptable while unpublished because the script overrides it).
   QA checks **5b** and **5c** enforce this, plus the live DOM check in **8**.
3. If you changed the extension files or `manifest.json`, regenerate
   `keel-extension.zip` (command above), upload it in the dashboard and let it
   be reviewed before pointing users at the new version.
4. Redeploy the static site (normal project process, e.g. merge/deploy to the
   configured Vercel project). Confirm `https://keel-desktop.vercel.app/keel-in-chrome`
   serves the updated page and the button opens the real listing.
5. Re-run QA: `python verify_keel_chrome.py` — expect 0 FAIL. Update
   `KEEL_CHROME_QA.md` with the fresh output and a READY verdict.

## Step 9 — Automated upload (optional)

The dashboard route above is sufficient and is the recommended path for the
first release. For scripted uploads/updates you need OAuth credentials:

1. Google Cloud Console → create/select a project → **Enable APIs** →
   **Chrome Web Store API**.
2. Configure the **OAuth consent screen** (external; add yourself as a test
   user if the app stays in testing).
3. Create an **OAuth client ID** (Desktop app or Web application) and obtain
   its **client ID and client secret**.
4. Request an access token with the scope
   `https://www.googleapis.com/auth/chromewebstore` and keep a refresh token
   so you can renew it. The API endpoints are under
   `https://chromewebstore.googleapis.com/api/v2/chromeitems` (create with
   `POST`, update a draft item with `PUT`, publish with
   `POST .../publish`). Listing text and image assets are usually still
   easiest to manage in the dashboard.
5. Store the client secret / refresh token **only** in a secret manager or
   environment variables of the CI runner. **Never commit credentials to the
   repo** — not in a config file, script, `.env`, log, screenshot, or QA
   report. Add any local credential files to `.gitignore`, rely on the repo's
   gitleaks pre-commit hook, and rotate any token that leaks. This QA script
   does not read or require any credentials.

---

## Security note (repeat)

The Chrome Web Store registration fee, OAuth client secret, refresh token and
access token are sensitive. Keep them out of source control and out of
agent-visible output. Publishing, payment and visibility changes require the
explicit approval of the repository owner; the QA tooling only verifies local
artifacts and never performs an upload.
