; Keel Desktop — NSIS installer include.
; Welcome page with the same words you'd see on a commercial installer,
; in the Keel brand. Per-user install, Start Menu + Desktop shortcut.

!macro customHeader
  ; keep wizard defaults; branding comes via build/header.bmp + sidebar.bmp
!macroend

!macro customInit
  ; nothing blocking; per-user install needs no elevation
!macroend

!macro customInstallMode
  ; per-machine install would demand elevation; per-user is default
!macroend

!macro afterRunUninstall
  ; ~/.keel is user data: never delete it on uninstall
!macroend

; ---------------------------------------------------------------------------
; Welcome / finish text (the "fully customized download experience" the
; user asked for). Shown with the sidebar image from build/sidebar.bmp.
; ---------------------------------------------------------------------------
!define MUI_FINAISHPAGE_TITLE "Keel is installed"
!define MUI_FINAISHPAGE_TEXT "Welcome to Keel — your agents, your files, your machine.$\r$\n$\r$\nEverything stays on this computer: the agent, the bridge, your conversations, your keys.$\r$\n$\r$\nClick Finish to launch Keel."

!define MUI_WELCOMEPAGE_TITLE "Welcome to Keel Setup"
!define MUI_WELCOMEPAGE_TEXT "This will install Keel 0.1.0 — a private, local, multi-agent coding workspace.$\r$\n$\r$\nKeel runs entirely on this machine. No account, no cloud relay, no telemetry.$\r$\n$\r$\nClick Next to continue."
