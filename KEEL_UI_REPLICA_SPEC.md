# KEEL UI replica spec (worktree copy)

Goal: Claude marketing UI/UX replicated exactly in layout, typography, colour,
content and interaction, on https://keel-desktop.vercel.app, with brand **Keel**
everywhere. The after-login app must keep the EXISTING KEEL DESKTOP DESIGN in the
repo (its own dark tokens, fonts, starburst) — do NOT make it look like Claude.

Site root: `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`

Brand map: Claude -> Keel; Anthropic -> Keel; "Try Claude" -> "Try Keel".
Keep model names Mythos/Fable, Opus, Sonnet, Haiku.

## Landing page — index.html + ui/landing.css + ui/landing.js
1. Header: Keel starburst + wordmark; nav triggers Product / Developers /
   Enterprise / Resources / Pricing (each with a mega dropdown, hover + click +
   keyboard, aria-expanded, Escape closes), Login, outlined "Contact sales",
   black "Try Keel". The download page's committed mega menus in
   `download.html` / `ui/download-clone.css` are the reference for menu content
   and styling — read them, mirror them with `l-` prefixed classes.
2. Hero, two columns: huge centred serif "Question what's next"; subtitle
   "Your thinking partner for big ambitions"; white login card (~380px) with
   outlined "G Continue with Google", divider "or", black "Continue with
   email", and fine print "By clicking continue, you agree to Keel's Privacy
   Policy and Terms of Service, and agree to receive occasional promotional
   emails and notifications." Beneath the card: "Download desktop app" button
   linking to `/download`. Right column: rounded hero image using existing
   `/assets/img/keel-app.jpg`.
3. "Explore plans" — centred serif heading; functional segmented toggle
   Individual | Team & Enterprise; four white cards with thin botanical line
   glyph, name, tagline, price, billing note, black "Try Keel" button, tiny
   "No credit card required", checkmark feature list; grey footnotes below:
   "* Usage limits apply. How fast you reach a limit depends on the model you
   use, how long your chats are and how large your files are. * No 5-hour limit
   for verified accounts. Prices shown do not include applicable tax. Prices
   and plans are subject to change at Keel's discretion."
   - Free / "Try Keel" / $0 / "Free for everyone": Limited usage every 5 hours
     and a limit on weekly usage (1000 billable hours, 120 billable monthly);
     Chat on web, desktop, and mobile; Search the web, create files, and run
     code; Memory across conversations; Connect apps and tools; Create
     Artifacts, Slides, Docs.
   - Pro / "For everyday work" / $17 / "Per month with annual subscription
     discount (billed annually)": Everything in Free, plus: More usage than
     Free, every 5 hours; Fast, paid access with more usage; Hands off and
     schedule tasks; Keel Code; Keel Science; Projects; Model choice; Keel
     Chrome and Microsoft 365.
   - Max / "For all-day work" / $100 / "Per month": Everything in Pro, plus:
     5x Pro usage every 5 hours and early access to new features; Higher limits
     — up to half your agency's work! New: build on the Keel Platform for New;
     $100 a month in API credits, Platform, new; Early access to advanced Keel
     features; Priority access at high traffic times.
   - Ultra / "For your largest tasks" / $200 / "Per month": Everything in Max,
     plus: 10x Pro usage every 5 hours*; 100+ Pro usage limits weekly*; $200 in
     monthly API credits, up from $100 on Max. New.
   - Team panel: Team $25/seat and Enterprise Custom cards.
4. FAQ — centred serif heading; 3 rows ~660px, thin rules, +/− icon, real
   answers: "What is Keel and how does it work?", "What should I use Keel
   for?", "How much does it cost to use?".
5. Dark #191919 footer: Keel wordmark; "How can we help today?" input with
   orange arrow (functional filter of links/FAQ); columns for Keel, Enterprise,
   Developers, Company, Terms and policies with all links from the Claude
   footer (Keel-branded); bottom bar "KEEL 2026 All rights reserved.", social
   icons, "Add to Preferred Sources", language select. Dismissible "Latest
   news" chip.
6. Functionality: all Try Keel / Login / Google / email / sales buttons open a
   validated in-page modal; success sets `keel_logged_in` in localStorage and
   offers a link to `/app`. No dead href="#" links, no console errors,
   responsive hamburger, focus-visible styles, aria attributes.

Real hrefs only: in-page anchors, `/download`, `/app`, `/privacy`, `/terms`,
`/notices`, `/roadmap`, `/eula`, `/trademark`, `/requirements`, `mailto:`.

## App surface — app.html + ui/style.css + ui/app.js
Keep Keel design. Target structure: sidebar with Keel logo/wordmark, New /
Search / Projects / Artifacts / Plugins and Recents + View all; account chip
"Elios · Free" + Upgrade; header "Free plan · Upgrade" pill; centered starburst
+ "You're here!"; composer placeholder "/ for skills", + attach, mic and voice
wave; beneath row Project / Sonnet 5.5 Medium / Auto; "Recent artifacts" with
View all and a card. Wire every new control with minimal, safe changes; keep
BYOK chat, settings, recents persistence and safety rules intact.
