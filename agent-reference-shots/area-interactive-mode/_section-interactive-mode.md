
---

# Area: Interactive TUI — input handling, key bindings, slash commands, @-mentions, file references, and the status line

**Primary source page:** https://code.claude.com/docs/en/interactive-mode.md
**Corroborating sources:**
- https://code.claude.com/docs/en/keybindings.md
- https://code.claude.com/docs/en/commands.md
- https://code.claude.com/docs/en/statusline.md
- https://code.claude.com/docs/en/common-workflows.md
- https://code.claude.com/docs/en/terminal-config.md
- https://code.claude.com/docs/en/env-vars.md
- https://code.claude.com/docs/en/sub-agents.md

**Method used:** public documentation fetched verbatim (the `.md` suffix serves plain markdown; 843 lines / 72,991 bytes cached at `agent-reference-shots/docs-cache/interactive-mode.md`); the same page rendered in a real browser and observed through **REA** over the Chrome DevTools Protocol (`list_browser_targets`, `inspect_web_page`, `capture_web_screenshot`); plus black-box observation of the published CLI's own TUI renderer via `claude --bg` + `claude logs`.

**Compliance:** no decompilation, no source extraction, no source-map dumping, no binary modification, no credential/licence/account reads. Only public docs and the published CLI's own user-visible surfaces. See `agent-reference-shots/TERMS-NOTES.md`.

**Environment caveat (applies to every claim below):** this host runs Claude Code 2.1.306 against a custom `ANTHROPIC_BASE_URL` serving a third-party model (`minimax/minimax-m3.1-flash:free`), not `api.anthropic.com`. Subscription-gated surfaces (the "You should know" mod, agent teams, cross-session messaging, usage-limit auto-continue) are therefore **documented but not independently observable here**, and are labelled OBSERVED-DOC accordingly.

---

## 1. Executive summary

The interactive TUI is a **multi-surface input system with a strict, documented contract**, not a free-form chat box. The page specifies roughly 40 global control shortcuts, 12 readline-style editing shortcuts, 5 alternative multiline-entry methods, 5 "quick command" prefix characters, a full vim modal editor, a 120-row slash-command menu with a documented fuzzy-matching algorithm, an `@` file-reference typeahead, a context-sensitive footer/status area, and a dozen auxiliary panels (transcript viewer, diff panel, diff dialog, `/btw` side-question overlay, task checklist, session recap, usage-limit wait, PR/MR badge, issue-reference hyperlinks).

Five properties are worth carrying into any reimplementation, because they are the ones that are hard to rediscover and easy to get wrong:

1. **Input is context-sensitive, not a single keymap.** The reference product has a *dispatch* model: a keystroke is resolved against the *active context* (Chat, Autocomplete, Confirmation, Tabs, Transcript, HistorySearch, DiffPanel, Footer, ModelPicker, …), and the same key can mean different things in different contexts. The keybindings file exposes **27 named contexts** and ~180 named actions with `namespace:action` identifiers. This is the single most important structural fact for a reimplementation, and it is documented on a *sibling* page, not on this one.

2. **The prompt is a queue, not a channel.** Typing while the agent is busy **queues** the message instead of interrupting; `Esc` interrupts; `Ctrl+Enter` / `Ctrl+X Ctrl+S` force-send. Messages are delivered at *tool-call boundaries within the same turn*, not at turn ends. This is the interaction model that makes a coding agent feel collaborative, and it is fully specified here.

3. **Every key has a documented terminal-portability answer.** Multiline entry has 5 methods; `Ctrl+X Ctrl+S` exists purely because "Terminals that don't report extended keys deliver `Ctrl+Enter` as plain `Enter`"; `Alt+M` exists because "Windows without VT mode (Node <24.2.0/<22.17.0, Bun <1.2.23)" loses `Shift+Tab`. A reimplementation that binds one key and assumes a modern terminal will be broken on a large fraction of real terminals.

4. **The footer is a live, priority-ordered hint surface.** Observed directly in this session's TUI capture: the footer line reads `⏸ manual mode on · ← for agents`, then gains `· esc to interrupt` while a turn is running, and degrades to `⏸ manual mode on · ? for shortcuts` when idle. The status line (a *different* surface) is a user-supplied script; the footer is built-in. The statusline doc states the status line "renders in its own row above the built-in footer badges and does not replace them", and that a custom status line suppresses "most of the footer's keyboard hints".

5. **`@` is a content-injection mechanism, not just a path picker.** A `@` mention of a file causes Claude Code to **expand the file's contents into the conversation** (subject to a 25,000-token Read limit and a 256 KB file cap); a directory mention expands to a *listing*, not contents; an `@server:resource` mention pulls an MCP resource. It also pulls in `CLAUDE.md` files from the file's directory and parent directories. This is a specific, contract-bearing behaviour that a reimplementation must decide about deliberately.

The page is **not thin** — it is one of the more detailed reference pages in the docs set, and it is the definitive source for the TUI's *observable contract*. It is, however, **not** the definitive source for the *status line* (that is `statusline.md`) nor for the *keybinding action vocabulary* (that is `keybindings.md`); this page links out to both repeatedly.

---

## 2. Detailed findings

### F-I1 — The input system is context-dispatched, with named contexts and named actions

**Status: OBSERVED-DOC** (this page for the dispatch model; `keybindings.md` for the enumeration)

Source: https://code.claude.com/docs/en/interactive-mode.md § "General controls", and https://code.claude.com/docs/en/keybindings.md § "Contexts" / § "Available actions".

This page repeatedly qualifies a shortcut by context rather than listing one global map:

> | `Tab` | Accept an autocomplete suggestion, or add a comment to a permission answer | While autocomplete suggestions are showing in the prompt input, accepts the selected suggestion. On most permission prompts, with **Yes** or **No** focused, opens a comment field on that option, and pressing it again closes the field. |

> | `Esc` | Interrupt Claude, or close a dialog | Stop the current response or tool call mid-turn so you can redirect. Claude keeps the work done so far. … While a footer item is selected, such as a row in the [subagent panel] below the prompt, `Esc` [deselects it] instead of interrupting. |

> | `Up/Down arrows` or `Ctrl+P`/`Ctrl+N` | Move cursor or navigate command history | When the input spans more than one visual row, whether wrapped or multiline, first moves the cursor within the prompt. Once the cursor is on the first or last visual row, pressing again navigates command history. |

The sibling page enumerates the vocabulary precisely. `keybindings.md` § "Contexts" lists **27 contexts**, each with an exact identifier string:

`Global`, `Chat`, `Autocomplete`, `Settings`, `Confirmation`, `Tabs`, `Help`, `Transcript`, `HistorySearch`, `Task`, `ThemePicker`, `Attachments`, `Footer`, `MessageSelector`, `DiffDialog`, `DiffPanel`, `ModelPicker`, `EffortSlider`, `Select`, `Plugin`, `AbovePrompt`, `AbovePromptInput`, `AbovePromptSelect`, `Pane`, `PaneField`, `Agents`, `Scroll`.

And § "Chat actions" gives the action namespace with exact defaults:

| Action | Default | Description (abridged) |
| :- | :- | :- |
| `chat:cancel` | Escape | Cancel current input |
| `chat:clearInput` | Ctrl+L | Force a full screen redraw, preserving input and conversation |
| `chat:clearScreen` | Cmd+K | Same as `chat:clearInput` |
| `chat:killAgents` | Ctrl+X Ctrl+K | Stop all running background subagents … Press the shortcut twice within 3 seconds to confirm |
| `chat:cycleMode` | Shift+Tab\* | Cycle permission modes |
| `chat:modelPicker` | Meta+P | Open model picker |
| `chat:fastMode` | Meta+O | Toggle fast mode |
| `chat:thinkingToggle` | Meta+T | Toggle extended thinking |
| `chat:submit` | Enter | Submit message |
| `chat:queueSubmit` | Ctrl+X Enter | Submit the message, marked to wait its turn … Unlike `chat:submit`, it submits the draft even while an autocomplete suggestion is highlighted. Requires v2.1.247 or later |
| `chat:sendNow` | Ctrl+Enter, Ctrl+X Ctrl+S | Send your queued messages … Requires v2.1.275 or later |
| `chat:newline` | Ctrl+J | Insert a newline without submitting |
| `chat:undo` | Ctrl+_, Ctrl+Shift+- | Undo last action |
| `chat:externalEditor` | Ctrl+G, Ctrl+X Ctrl+E | Open in external editor |
| `chat:stash` | Ctrl+S | Stash current prompt |
| `chat:imagePaste` | Ctrl+V (Alt+V on Windows and WSL) | Paste image from clipboard. On WSL, both shortcuts are bound by default |

Verbatim footnote from `keybindings.md`:

> \*On Windows without VT mode (Node \<24.2.0/\<22.17.0, Bun \<1.2.23), defaults to Meta+M.

Config file, verbatim from `keybindings.md` § "Configuration file":

> Run `/keybindings` to create or open your configuration file at `~/.claude/keybindings.json`.
>
> The keybindings configuration file is an object with a `bindings` array. Each block specifies a context and a map of keystrokes to actions.
>
> **Changes to the keybindings file are automatically detected and applied without restarting Claude Code.**

```json theme={null}
{
  "$schema": "https://www.schemastore.org/claude-code-keybindings.json",
  "$docs": "https://code.claude.com/docs/en/keybindings",
  "bindings": [
    {
      "context": "Chat",
      "bindings": {
        "ctrl+e": "chat:externalEditor",
        "ctrl+s": null
      }
    }
  ]
}
```

Note the **unbind idiom**: the value `null` removes a default binding. And note that a `keybindings.json` naming an action the product does not implement "remains valid" rather than erroring (`keybindings.md` § "Confirmation actions" explicitly lists `confirm:previousField` as "(unbound) | Claude Code doesn't respond to this action, and a `keybindings.json` that names it remains valid").

**Why a reimplementer needs this:** the *contract* is "a keystroke resolves to an action within the active context"; the *vocabulary* is a separate, extensible, user-editable file. A flat single-keymap implementation will not reproduce the observable behaviour (e.g. `Esc` in a footer panel vs. `Esc` interrupting a turn).

---

### F-I2 — The prompt input is a queue with a documented delivery order

**Status: OBSERVED-DOC**

Source: § "Queue messages while Claude works", § "When Claude Code sends what you queued", § "Take back what you queued".

> Type a message and press `Enter` while Claude is working. Claude Code queues the message instead of interrupting the turn, and lists the queued entries in the conversation until it sends them. You can queue `!` [shell commands] and most [commands] the same way, apart from the commands, such as `/status`, that Claude Code runs as soon as you send them.

> Sent and queued messages show in gray until Claude starts responding to them, so you can tell which messages Claude hasn't started on yet.

The delivery rules, quoted:

> * Messages: if you queue a message while Claude is running tool calls, Claude Code passes it to Claude as soon as those tool calls finish, within the same turn. When the turn ends with messages still queued, they go out without another key press, in the order you typed them
> * Commands and shell commands: Claude Code holds them until the turn ends, then runs them one at a time, keeping the order you queued them in

> To send what you queued without waiting, press `Ctrl+Enter`. Your queued messages go out right away, with your draft queued behind them if you had typed one. Requires Claude Code v2.1.275 or later.

> If you queued a `!` shell command ahead of your messages, the key interrupts the turn. Otherwise, what happens to the turn depends on what Claude is doing when you press the key:
>
> * Running shell commands, subagents, or other work that can move to the [background]: that work moves to the background and keeps running, and Claude reads your messages in the same turn
> * Only writing a response, or running something that can't move to the background: Claude Code interrupts the turn and sends your messages next. Before v2.1.281, the key interrupted the turn in both cases

Take-back semantics:

> Press `Up` from the first line of the input box to take back the queued messages and commands. Claude Code removes them from the queue and puts them in the input box, one per line, ahead of any text you had typed. Edit the text and press `Enter` to queue it again as one entry, or clear the input box to drop it.

> Claude Code takes back queued shell commands only when the input box is empty and you have nothing else queued, and it switches the input box to shell mode when it does.

**Why a reimplementer needs this:** this is a *state machine*, not a UI affordance. A reimplementation needs an explicit queue of pending user turns with a per-entry kind (message / command / shell-command), a delivery policy that depends on the agent's current activity, and a "take back" operation that mutates both the queue and the input buffer atomically. The "sent and queued messages show in gray" rule is the visible projection of that state and must be part of the contract.

---

### F-I3 — Five documented methods for multiline input, and why each exists

**Status: OBSERVED-DOC**

Source: § "Multiline input".

| Method | Shortcut | Context |
| :- | :- | :- |
| Quick escape | `\` + `Enter` | Works in all terminals |
| Option key | `Option+Enter` | After enabling Option as Meta on macOS |
| Shift+Enter | `Shift+Enter` | Native in iTerm2, WezTerm, Ghostty, Kitty, Warp, Apple Terminal, Windows Terminal. For other terminals, see Enter multiline prompts |
| Control sequence | `Ctrl+J` | Works in any terminal without configuration |
| Paste mode | Paste directly | For code blocks, logs |

And the general-controls entry for `Ctrl+Enter` / `Ctrl+X Ctrl+S`:

> | `Ctrl+Enter` or `Ctrl+X Ctrl+S` | Send queued messages now | … In terminals that don't report extended keys, `Ctrl+Enter` arrives as plain `Enter`; `Ctrl+X Ctrl+S` works in any terminal. Requires Claude Code v2.1.275 or later |

**Why a reimplementer needs this:** the *observable contract* is "there is always a multiline path that works in the user's terminal, plus a universal fallback". A reimplementation should expose a **multiline-trigger list** (not a single binding), and should offer a chord fallback (`Ctrl+X Ctrl+S`) for terminals with broken extended-key reporting. This is a portable-UI problem, solved idiomatically by making the newline trigger a user-configurable *set*.

---

### F-I4 — Readline editing conventions, with an exact word-boundary rule and a deprecated escape hatch

**Status: OBSERVED-DOC**

Source: § "Text editing", § "Word boundaries in editing shortcuts".

> | `Ctrl+K` | Delete to end of line | Stores deleted text for pasting |
> | `Ctrl+U` | Delete from cursor to line start | Stores deleted text for pasting. Repeat to clear across lines in multiline input. On macOS, terminal emulators including iTerm2 and Terminal.app map `Cmd+Backspace` to this shortcut |
> | `Ctrl+W` | Delete back to previous whitespace | Stores deleted text for pasting. One press removes a whole path or `--flag=value`. To delete only the previous word, press `Option+Delete` on macOS or `Ctrl+Backspace` on Windows |
> | `Ctrl+Y` | Paste deleted text | Pastes the text you last deleted with one of the word or line deletion shortcuts, such as `Ctrl+K`, `Ctrl+U`, or `Ctrl+W` |
> | `Alt+Y` (after `Ctrl+Y`) | Cycle paste history | After pasting, cycle through previously deleted text. Requires Option as Meta on macOS |
> | `Ctrl+_` or `Ctrl+Shift+-` | Undo last input edit | Restores the previous input text and cursor position |

The word-boundary rule is stated with a worked example — exactly the kind of detail that is unobvious and load-bearing:

> The word shortcuts `Alt+B`, `Alt+F`, `Alt+D`, `Option+Delete`, and `Ctrl+Backspace` treat a word as a run of letters and digits, so punctuation such as `_`, `.`, and `/` separates words. With `src/utils/foo.ts` in the prompt, repeated presses of `Alt+B` stop at the start of `ts`, `foo`, `utils`, and `src`.

> `Ctrl+W` is different: it ignores punctuation and deletes back to the previous whitespace, so one press removes all of `src/utils/foo.ts`.

> In text written without spaces, such as Chinese or Japanese, the word shortcuts still move or delete one word at a time.

> These readline conventions apply in Claude Code v2.1.261 and later. The [`keybindingFlavor`](/docs/en/settings-reference#keybindingflavor) setting that turned them on in earlier versions is deprecated and has no effect.

> You can't remap these shortcuts in the [keybindings configuration file](/docs/en/keybindings), which has no actions for them.

The last two paragraphs together say two things: **the readline word-motions are deliberately not remappable**, and the "kill-ring + paste-history" model (`Ctrl+K`/`Ctrl+U`/`Ctrl+W` → `Ctrl+Y` → `Alt+Y`) is a full readline kill-ring, not a simple clipboard.

**Why a reimplementer needs this:** the word-boundary rule is a *Unicode-aware* definition (letters and digits only; CJK has no spaces so a word is a code-point run). A reimplementation should implement a readline-compatible `WORD`-vs-`word` distinction and a kill-ring with history, and should accept that these cannot be remapped.

---

### F-I5 — Slash commands: a menu with a documented, non-trivial matching algorithm

**Status: OBSERVED-DOC**

Source: § "Commands", § "Complete a command mid-prompt"; and https://code.claude.com/docs/en/commands.md § "How the command menu matches what you type".

> Type `/` in Claude Code to see the commands available to you, or type `/` followed by any letters to filter. The `/` menu lists built-in commands, bundled and user-authored [skills], and commands contributed by [plugins] and [MCP servers]. Not all built-in commands are visible to every user since some depend on your platform or plan, and [a few available commands are hidden from the menu by design] and run when you type their full name.

> In [fullscreen rendering], the `/` command and `@` file suggestion lists also respond to the mouse: hovering highlights a row and clicking accepts it.

Mid-prompt completion:

> Command completion also works partway through a prompt: type `/` after a space, then the first letters of a name, as in `run the tests, then /com`. Only commands whose names start with those letters match, so a file path such as `/tmp/notes.md` doesn't keep a list open. Claude Code runs a command itself only when the command [starts your message].

> * **In [fullscreen rendering]**: the matches open as a list while you type, with no row highlighted, so `Enter` still sends your prompt as typed. Press `Tab` to insert the top match, or pick a row with the arrow keys and `Enter`.
> * **Outside fullscreen**: the rest of the top match appears as ghost text at your cursor, with a count such as `+2` when more commands match. Press `Tab` to insert the only match, or to open the list when several match, then pick a row with the arrow keys and `Enter`.

> In both renderers, press `Tab` on a bare mid-prompt `/` to list every command.

> A plugin skill matches on its bare name too, so `/deploy` finds a skill named `myplugin:deploy-app`. When you insert the match, Claude Code writes the full `/myplugin:deploy-app`.

The matching algorithm, from `commands.md` § "How the command menu matches what you type" (quoted verbatim — this is the highest-value single paragraph for a reimplementer):

> * **Highlighting**: Claude Code highlights the top suggestion only when the letters after the `/` match a command's name or alias, from the start of the name or from a word within it, ignoring the `:`, `_`, and `-` separators. Typing `/adddir` highlights `/add-dir`, and typing `/new` highlights `/clear` through its alias. Press `Enter` to run the highlighted suggestion. These highlighting rules require Claude Code v2.1.236 or later.
> * **After a typo**: Claude Code highlights nothing. The close matches stay listed, and you can pick one with `Tab` or the arrow keys, but `Enter` submits your text as typed and reports [Unknown command].
> * **Commands that aren't available to you**: Claude Code leaves them out of the menu. When nothing matches, Claude Code shows `No commands match "/name"`. Most unavailable commands return [Unknown command] when you submit them; a few, such as [`/schedule` on a Console API key], answer with their own availability message instead. Some commands also answer with a message of their own when your organization's policy disables them.
> * **Hidden commands**: Claude Code keeps a few available commands, such as `/heapdump`, out of the menu by design. A partial name never brings a hidden command into the menu: if the partial matches nothing visible, Claude Code shows the same no-match message. Claude Code lists the command only once you've typed its full name, and submitting the full name runs it.

**Why a reimplementer needs this:** the matching is *not* prefix matching and *not* substring matching. It is "match at the start of the name **or** at the start of a word within the name, with `:`, `_`, `-` treated as separators", and the **highlight** (which decides what `Enter` does) is a *stricter* predicate than the *list* (which decides what is visible). Two different predicates. A naive `startsWith` implementation will not reproduce `/adddir` → `/add-dir` or `/new` → `/clear`.

Also note the **command namespace is a merge of four sources** (built-in, skills, plugins, MCP prompts), that the display form is namespaced (`/myplugin:deploy-app`) while the *match* form is bare (`/deploy`), and that "hidden commands" exist and must remain hidden until fully typed.

---

### F-I6 — `@`-mentions: file path typeahead, and content expansion with hard limits

**Status: OBSERVED-DOC** (this page for the trigger; `common-workflows.md` for the expansion contract)

Source: § "Quick commands":

> | `@` | File path mention | Trigger file path autocomplete. In sessions with [cross-session messaging], when you type at least one letter after the `@`, Claude Code also suggests your other live sessions on this machine, so you can tell Claude to message the one you pick. Requires Claude Code v2.1.232 or later |

And § "Commands" adds: "In [fullscreen rendering], the `/` command and `@` file suggestion lists also respond to the mouse: hovering highlights a row and clicking accepts it."

The expansion contract, from https://code.claude.com/docs/en/common-workflows.md § "Reference files and directories" (verbatim):

> Use @ to quickly include files or directories without waiting for Claude to read them.
>
> **1. Reference a single file**
>
> ```text wrap theme={null}
> Explain the logic in @src/utils/auth.js
> ```
>
> This includes the content of the file in the conversation when it fits the [Read tool]'s token limit, 25,000 tokens by default. A text file larger than 256KB isn't included.
>
> **2. Reference a directory**
>
> ```text wrap theme={null}
> What's the structure of @src/components?
> ```
>
> **3. Reference MCP resources**
>
> ```text wrap theme={null}
> Show me the data from @github:repos/owner/repo/issues
> ```
>
> This fetches data from connected MCP servers using the format @server:resource.
>
> * File paths can be relative or absolute
> * Type `@` to open a path suggestion menu, then press Enter or Tab to accept the highlighted path and Enter again to send the message
> * @ file references add `CLAUDE.md` in the file's directory and parent directories to context
> * Directory references show file listings, not contents
> * You can reference multiple files in a single message (for example, "@file1.js and @file2.js")
>
> To stop `@` references from including file contents and directory listings in your message, set [`CLAUDE_CODE_DISABLE_FILE_MENTIONS=1`] in your shell or user settings. Claude then receives the paths you referenced with a note to read them using its file tools. The variable requires Claude Code v2.1.299 or later, and Claude Code ignores it in project and local settings.

Related, from `env-vars.md`:

> | `CLAUDE_CODE_DISABLE_ATTACHMENTS` | Set to `1` to disable attachment processing. File mentions with `@` syntax are sent as plain text instead of being expanded into file content. Ignored in [project and local settings] |
> | `CLAUDE_CODE_DISABLE_FILE_MENTIONS` | Set to `1` to stop Claude Code from expanding [`@` mentions] of files and directories. Claude instead gets the mentioned paths with a note to read them using its file tools. Ignored in [project and local settings]. Requires Claude Code v2.1.299 or later |

And the `@`-mention also has an *agent* meaning, from `sub-agents.md` § "Choose the subagent":

> **@-mention the subagent.** Type `@` and pick the subagent from the typeahead, the same way you @-mention files. …
>
> ```text wrap theme={null}
> @"code-reviewer (agent)" look at the auth changes
> ```
>
> Your full message still goes to Claude, which writes the subagent's task prompt based on what you asked. The @-mention controls which subagent Claude invokes, not what prompt it receives.

> You can also type the mention manually without using the picker: `@agent-<name>` for local subagents, or `@agent-` followed by the scoped name for plugin subagents, for example `@agent-my-plugin:code-reviewer`. While you type this form the typeahead shows file matches rather than agents. The agent mention still resolves when you submit.

**Why a reimplementer needs this:** the `@` typeahead is a **multi-kind namespace** (files, directories, MCP resources `server:resource`, subagents, other live sessions) whose *resolution* has real side effects (content injection, `CLAUDE.md` injection, MCP fetches, agent selection). A reimplementation must:
- keep the *typeahead* (a fuzzy path matcher with filesystem access) separate from the *resolution* (what the mention means when submitted);
- implement the file-size and token caps (256 KB / 25,000 tokens);
- distinguish "directory → listing" from "file → content";
- support `@server:resource` and `@agent-name` disambiguation, including the fact that the typeahead shows *files* while typing `@agent-` but the mention still resolves as an agent.

---

### F-I7 — The status area: a built-in footer of context-sensitive hints, separate from the user scriptable status line

**Status: OBSERVED-CLI** (footer text) + **OBSERVED-DOC** (the status line contract)

Source: OBSERVED-CLI — this session's own TUI capture, `agent-reference-shots/tui-background-session-raw.txt`, produced by running the published CLI with `claude --bg` and reading `claude logs`. The footer row, verbatim, with ANSI stripped:

```
● high · /effort
────────────────────────────────────────────────────────────────────────────────────────────────────────  ⏸ manual mode on · ← for agents
```

and, once a turn was running:

```
────────────────────────────────────────────────────────────────────────────────────────────────────────  ⏸ manual mode on · ← for agents · esc to interrupt
```

and, in a third frame of the same session:

```
────────────────────────────────────────────────────────────────────────────────────────────────────────  ⏸ manual mode on · ? for shortcuts
```

The same three footer variants appear in `agent-reference-shots/tui-startup-banner.txt`.

**INFERRED** (reasoning: the three captured variants differ only in the trailing hint segment, and the status-line doc explicitly names the exact hint strings `esc to interrupt` and the `? for shortcuts` fallback as "the footer's keyboard hints") — the footer is a **priority-ordered hint surface**: it always shows the permission-mode indicator, then appends contextual hints in order of what the user most likely needs *right now* (interrupt affordance while busy; agent-view and shortcut-help affordances while idle). The observed `⏸ manual mode on` string corresponds to the doc's statement that `default` is "labeled Manual in the mode indicator".

Source: OBSERVED-DOC, § "General controls":

> | `Shift+Tab`, or `Alt+M` on Windows when the Node or Bun runtime doesn't enable VT input mode | Cycle permission modes | Cycle through `default` (labeled Manual in the mode indicator), `acceptEdits`, `plan`, and, when available, `bypassPermissions` and then `auto`. From `auto`, the first press switches to `default`. |

and § "PR review status":

> When working on a branch with an open pull request, Claude Code displays a clickable PR link in the footer, such as "PR #446". The link has a colored underline indicating the review state:
>
> * Green: approved
> * Yellow: pending review
> * Red: changes requested
> * Gray: draft
>
> The badge disappears once the pull request merges or closes.

> `Cmd+click` (macOS) or `Ctrl+click` (Windows/Linux) the link to open the pull request in your browser.

and § "GitLab merge requests":

> When you work on a branch with an open GitLab merge request, Claude Code shows a clickable `MR !N` badge in the footer slot that otherwise holds the GitHub PR link. `!N` is GitLab's own reference syntax for merge request number N.

Now the *status line* — a **separate** surface, documented at https://code.claude.com/docs/en/statusline.md:

> The status line is a customizable bar at the bottom of Claude Code that runs any shell script you configure. It receives JSON session data on stdin and displays whatever your script prints, giving you a persistent, at-a-glance view of context usage, costs, git status, or anything else you want to track.

> The status line renders in its own row above the built-in footer badges and does not replace them. With a custom status line configured, Claude Code stops showing most of the footer's keyboard hints, including `esc to interrupt`, the `? for shortcuts` fallback, and the `hold space to speak` [voice dictation] hint. To add clickable link badges to the footer when an ID appears in the conversation, without writing a script, configure [`footerLinksRegexes`] instead.

> Claude Code runs your script with [JSON session data] on stdin and displays whatever the script prints to stdout.
>
> The status line runs locally and does not consume API tokens. It temporarily hides during certain UI interactions, including the help menu and permission prompts.

> Claude Code debounces updates at 300ms, so rapid changes batch together and your script runs once after the changes stop. A change to the `command` itself skips the debounce: Claude Code runs the new command right away. If a new update triggers while your script is still running, Claude Code cancels the in-flight script.

> Claude Code captures your script's output instead of connecting it directly to the terminal, so `tput cols` and language-level width detection cannot read the terminal size from inside the script. Read the `COLUMNS` and `LINES` environment variables instead. Claude Code sets these to the current terminal dimensions before running your script.

The JSON field vocabulary delivered on stdin is large and exact (`statusline.md` § "Available data"), including e.g. `model.id`, `model.display_name`, `cwd`, `workspace.current_dir`, `workspace.project_dir`, `workspace.added_dirs`, `workspace.git_worktree`, `workspace.repo.host`, `workspace.repo.owner`, `workspace.repo.name`, `cost.total_cost_usd`, `cost.total_duration_ms`, `cost.total_api_duration_ms`, `cost.total_lines_added`, `cost.total_lines_removed`, `context_window.total_input_tokens`, `context_window.total_output_tokens`, `context_window.context_window_size`, `context_window.used_percentage`, `context_window.remaining_percentage`, `context_window.current_usage`, `exceeds_200k_tokens`, `fast_mode`, `effort.level`, `thinking.enabled`, `rate_limits.five_hour.used_percentage`, `rate_limits.five_hour.resets_at`, `rate_limits.seven_day.used_percentage`, `rate_limits.seven_day.resets_at`, `rate_limits.spend_limit.used_percentage`, `rate_limits.spend_limit.resets_at`, `rate_limits.spend_limit.used_usd`, `rate_limits.spend_limit.limit_usd`, `rate_limits.spend_limit.period`, `prompt_cache`, `session_id`, `session_name`, `prompt_id`.

**Why a reimplementer needs this:** the footer and the status line are **two different extension points with different ownership** — the footer is product-owned and hint-driven; the status line is user-owned, script-driven, JSON-fed, debounced at 300 ms, and re-runs on a documented trigger list. A reimplementation that merges them will get the "custom status line suppresses the footer's keyboard hints" behaviour wrong, and will miss that the status line is *above* the footer, not replacing it.

---

### F-I8 — `Esc` semantics: five distinct behaviours from one key, distinguished by state

**Status: OBSERVED-DOC**

Source: § "General controls", § "General controls" (`Esc` + `Esc`), § "Vim editor mode".

> | `Esc` | Interrupt Claude, or close a dialog | Stop the current response or tool call mid-turn so you can redirect. Claude keeps the work done so far. If you have [messages queued], Claude Code sends them next. When a dialog is open, `Esc` closes the dialog. While a footer item is selected, such as a row in the [subagent panel] below the prompt, `Esc` [deselects it] instead of interrupting. On a permission prompt, `Esc` declines the action, the same as [**No** without a comment] |

> | `Esc` + `Esc` | Clear input draft, or rewind | When the prompt input contains text, double `Esc` clears it and saves the draft to history so `Up` recalls it. When the input is empty, double `Esc` opens the [rewind menu] to restore or summarize code and conversation from a previous point |

> | `Ctrl+C` | Interrupt, or clear input | Interrupts a running operation. If nothing is running, the first press clears the prompt input and a second press exits Claude Code. To get a cleared draft back, see [Bring back a cleared draft] |

> | `Ctrl+D` | Exit Claude Code session | The first press shows a confirmation hint and a second press within 800ms exits. When the prompt has text, `Ctrl+D` deletes the character after the cursor instead |

The "double press" idiom is a *general* pattern with different time windows per key: `Ctrl+D` = 800 ms, `Ctrl+X Ctrl+K` = 3 seconds, `Esc+Esc` = implied. And the draft-recovery contract:

> To get back a draft you cleared with `Ctrl+C`, press `Up`, either right away or after you've sent a message or command:
>
> * **Right after clearing the draft**: press `Up` once while the prompt is still empty. Requires Claude Code v2.1.288 or later.
> * **After sending a message or command**: press `Up` to step back to the draft. Claude Code keeps the ten most recent cleared drafts for the current session, with their pasted text and images, and discards them when you exit. Requires Claude Code v2.1.292 or later.

**Why a reimplementer needs this:** "cancel" is not one behaviour. A reimplementation needs an explicit state machine over (dialog open? footer item selected? permission prompt open? turn running? input non-empty?) and a **timed double-press** primitive with a per-key window.

---

### F-I9 — Command history: per-directory, cross-session, de-duplicated, with a separate cleared-draft ring

**Status: OBSERVED-DOC**

Source: § "Command history", § "Bring back a cleared draft", § "Reverse search with Ctrl+R".

> Claude Code keeps a history of the prompts you type, and Up-arrow recall reaches prompts from past sessions of the same project:
>
> * Input history is stored per working directory
> * Running `/clear` starts a new session: recall then lists the new session's prompts first, with earlier sessions' prompts after them. The previous session's conversation is preserved and can be resumed.
> * Submitting the same prompt twice in a row records one history entry, so pressing Up steps to the previous distinct prompt
> * When you recall a prompt that included pasted text, Claude Code sends the full pasted content again when you resubmit. If the content has since been [cleaned up], Claude Code doesn't send the literal `[Pasted text #N]` string
> * History expansion with `!` is disabled by default

Reverse search differs between renderers:

> Press `Ctrl+R` to interactively search through your command history. In [fullscreen rendering], `Ctrl+R` opens a search dialog instead: type to filter, press `Up` and `Down` to move through matches, and press `Ctrl+S` to cycle the scope through this session, this project, and all projects. Press `Enter` or `Tab` to place a match in the prompt input, or `Esc` to cancel.

> The inline search scans your full prompt history, newest first, with duplicates collapsed to the newest occurrence. The fullscreen dialog searches your whole prompt history in the selected scope, newest first, with duplicates collapsed to the newest occurrence: the most recent prompts appear immediately, and matches from older prompts fill in as Claude Code loads the rest.

> Accepting a match or canceling the search takes effect immediately, even while Claude Code is still loading the history.

**Why a reimplementer needs this:** history is keyed by *working directory*, spans *sessions* (so `--resume`/`--continue` and `/clear` interact with it), and has **two separate rings** — the prompt history and the ten-entry cleared-draft ring. The "submitting the same prompt twice in a row records one history entry" rule means the history key is the *content*, not a sequence of events.

---

### F-I10 — Vim mode is a full modal editor with text objects, and one documented restriction

**Status: OBSERVED-DOC**

Source: § "Vim editor mode".

> Enable vim-style editing via `/config` → Editor mode.
>
> Claude Code keeps your vim mode and cursor position when you toggle the [transcript viewer] with `Ctrl+O` or open and close a panel such as `/config`. If you leave the prompt in NORMAL mode, it's still in NORMAL mode when you return, with the cursor where you left it.

Mode switching table: `Esc` or `Ctrl+[` → NORMAL (from INSERT, VISUAL); `i`/`I`/`a`/`A`/`o`/`O` insert variants; `v`/`V` start visual selections.

Navigation (NORMAL): `h/j/k/l`, `Space`, `w/e/b`, `0/$/^`, `gg/G`, `f{char}/F{char}/t{char}/T{char}`, `;`/`,` repeat, `%` jump to matching bracket (requires v2.1.301+), `/` reverse history search.

Editing (NORMAL): `x`, `r{char}`, `dd`, `D`, `dw/de/db`, `df{char}/dt{char}`, `dj/dk`, `dgg/dG`, `d0/c0/y0` (v2.1.281+), `d%/c%/y%` (v2.1.301+), `cc`, `C`, `cw/ce/cb`, `s`, `S`, `yy/Y`, `yw/ye/yb`, `p/P`, `>>/<<`, `J`, `u`, `.`.

Text objects: `iw/aw`, `iW/aW`, `i"/a"`, `i'/a'`, `i(/a(`, `i[/a[`, `i{/a{`.

Visual mode: `d/x`, `y`, `c/s`, `p`, `r{char}`, `~/u/U`, `>/<`, `J`, `o` (swap cursor and anchor), text objects, `v/V` toggle.

> Block-wise visual mode with `Ctrl+V` is not supported.

The INSERT-mode remap mechanism is documented with an exact settings schema:

> The [`vimInsertModeRemaps`] setting maps a two-key INSERT-mode sequence to Escape, so a mapping like `jj` returns you to NORMAL mode.
>
> The following `~/.claude/settings.json` example turns on vim mode and maps `jj` to Escape:
>
> ```json theme={null}
> {
>   "editorMode": "vim",
>   "vimInsertModeRemaps": { "jj": "<Esc>" }
> }
> ```
>
> Each key is exactly two printable characters typed in sequence, and `"<Esc>"` is the only supported target. Entries with a different length or target are ignored.
>
> Typing the first character of a sequence inserts it normally. Pressing the second character within one second removes that pending character and switches to NORMAL mode, leaving neither character in your input. After the one-second window, or if a different key follows, both characters stay as literal text, so you can still type a word containing the sequence by pausing between the two keys.
>
> Claude Code reads this setting from your user settings file, the `--settings` flag, and [managed settings] only. Entries in a project's `.claude/settings.json` or `.claude/settings.local.json` are ignored, so a checked-out repository can't remap your keystrokes.

**Why a reimplementer needs this:** vim mode is a *large* surface (~70 bindings + 14 text objects), it survives panel transitions, and the INSERT-mode remap is a **prefix-timer** mechanism with a 1-second window — including the specific behaviour that a mismatched second key leaves *both* characters as literal text. The security-relevant detail (project settings are ignored) should be preserved.

---

### F-I11 — The transcript viewer has its own keymap, split across two renderers

**Status: OBSERVED-DOC**

Source: § "Transcript viewer".

> When the transcript viewer is open (toggled with `Ctrl+O`), these shortcuts are available. Run `/tui` with no argument to check which renderer is active. `Ctrl+E` can be rebound via [`transcript:toggleShowAll`].

| Shortcut | Description |
| :- | :- |
| `?` | Toggle the keyboard shortcut help panel. Requires [fullscreen rendering] |
| `{` / `}` | Jump to the previous or next user prompt, like vim paragraph motion. Requires [fullscreen rendering] |
| `Ctrl+E` | Toggle show all content. Available in the classic renderer only, not in [fullscreen rendering] |
| `[` | Write the full conversation to your terminal's native scrollback so `Cmd+F`, tmux copy mode, and other native tools can search it. Requires [fullscreen rendering] |
| `v` | Write the conversation to a temporary file and open it in `$VISUAL` or `$EDITOR`. Requires [fullscreen rendering] |
| `q`, `Ctrl+C`, `Esc` | Exit transcript view. All three can be rebound via [`transcript:exit`] |

And the `Ctrl+O` description, which defines what the viewer *shows*:

> | `Ctrl+O` | Toggle transcript viewer | Shows detailed tool usage and execution, with a timestamp and the model used on each assistant message. Also expands lines that collapse by default, such as MCP calls, shown as a single `Called slack 3 times` line, and [messages from your other sessions], shown as a one-line `Message from @<sender>` preview |

**Why a reimplementer needs this:** the product has (at least) **two renderers** — "classic" and "fullscreen" — and the *same key has different meanings or availability* in each (`Ctrl+E` is classic-only; `?`, `{`/`}`, `[`, `v` are fullscreen-only). The renderer is inspectable at runtime via `/tui` with no argument. A reimplementation that assumes one renderer will not match the documented behaviour.

---

### F-I12 — Shell mode (`!`), a distinct input mode with its own autocomplete and sandbox exemption

**Status: OBSERVED-DOC**

Source: § "Shell mode with `!` prefix".

> Run shell commands directly without going through Claude by prefixing your input with `!`:
>
> ```bash theme={null}
> ! npm test
> ! git status
> ! ls -la
> ```
>
> Shell mode:
>
> * Adds the command and its output to the conversation context
> * Shows real-time progress and output
> * Supports the same `Ctrl+B` backgrounding for long-running commands
> * Doesn't require Claude to interpret or approve the command
> * Supports history-based autocomplete: type a partial command and press `Tab` to complete from previous `!` commands in the current project
> * Supports live file path autocomplete: type a token containing a forward slash, such as `./src/` or `~/`, to see a dropdown of matching files and directories, then press `Tab` to accept. Use forward slashes on Windows too; the dropdown is triggered by `/`, not `\`
> * Exit with `Escape`, `Backspace`, or `Ctrl+U` on an empty prompt
> * Pasting text that starts with `!` into an empty prompt enters shell mode automatically, matching typed `!` behavior

> Unless your session is one of those listed under [strict sandbox mode], commands you type in shell mode run outside the [sandbox] even when you've enabled sandboxing, because the sandbox applies to the commands Claude runs.

> Claude responds to the command output automatically once it lands in the transcript, so you can run `! npm test` and get an explanation of the failures without a second prompt. The response costs the same as sending a normal prompt. To add the output to context without a response instead, set [`respondToBashCommands`] to `false` in `settings.json`.

**Why a reimplementer needs this:** shell mode is a **mode of the input box**, with its own completion sources (history of `!` commands in the current project; live filesystem paths), its own exit keys, its own paste semantics, and a **documented sandbox escape** ("commands you type in shell mode run outside the sandbox even when you've enabled sandboxing"). The sandbox exemption is a security-relevant fact a reimplementer must decide about explicitly rather than inherit by accident.

---

### F-I13 — `/diff` exists in two forms, with a documented turn-attribution model

**Status: OBSERVED-DOC**

Source: § "Review changes with /diff".

> Run `/diff` to look over the changes in your working tree without leaving Claude Code. You see the edits Claude has made so far alongside anything else you haven't committed. What `/diff` opens depends on which renderer is active:
>
> * **[Fullscreen rendering]**: the [diff panel] opens beside the conversation. It stays open and updates while you keep working.
> * **Classic renderer**: the [diff dialog] opens above the prompt, and you close it when you're done reading.
>
> The panel and the dialog both come from `cc-plugin-diff`, one of the [mods built into Claude Code]. If you disable that mod in `/plugin`, `/diff` opens Claude Code's earlier panel and [diff viewer] instead.

> In the changes `/diff` reads from git, a submodule appears as a single entry, and only when the commit it points to changes; edits to files inside the submodule don't appear there. The panel and the dialog also offer a view of each turn's edits once Claude has edited files. These turn views come from Claude's file edits rather than from git, so a change Claude makes through a shell command appears only under `Current`, the working-tree view.

Diff panel specifics:

> To use the panel you need:
>
> * [Fullscreen rendering]
> * A git repository
> * A terminal at least 110 columns wide
> * Claude Code v2.1.287 or later
>
> The panel also opens on its own once Claude starts editing files, if your terminal is at least 144 columns wide. After you've opened it yourself with `/diff`, later sessions open it as soon as Claude edits a file in any terminal wide enough to fit it. Close the panel and it stays closed, in this session and later ones, until you run `/diff` again.

> * **Change what the panel compares against**: press `Ctrl+X B` to cycle from this session's changes, to your uncommitted changes as one list, to everything since your branch split from the default branch. Claude Code remembers the choice for each repository.

> The panel lists the changed files with their added and removed line counts, and shows each file's diff under the list. Claude Code refreshes it each time Claude edits a file or runs a shell command.

Turn views:

> Once Claude has edited files, a `source` picker appears above the list. It offers one turn view, labeled `T1`, `T2`, and so on, for each of your prompts that led Claude to edit files. A turn view shows only that turn's edits, and `Current` returns you to the working tree.

**Why a reimplementer needs this:** there are **two sources of truth for "what changed"** — git (working tree) and the agent's own file-edit log (per-turn). The UI exposes both, labelled `Current` vs `T1`/`T2`. A reimplementation must record per-turn edit attribution separately from git, and must know that shell-command-made changes are *not* attributable to a turn. The width thresholds (110 / 144 columns) are also part of the observable behaviour.

---

### F-I14 — `/btw`: a side question with a separate context, no tools, and a bounded replay

**Status: OBSERVED-DOC**

Source: § "Side questions with /btw".

> Use `/btw` to ask a question about your current work without adding to the conversation history.
>
> ```
> /btw what was the name of that config file again?
> ```
>
> Claude answers a side question from what's already in the conversation: your messages, its replies, and the tool results it has gathered. You can ask about code Claude has already read, decisions it made earlier, or anything else from the session. A later side question also sees your earlier side questions: Claude Code replays the newest 20 exchanges with each ask, until you clear them. The question and answer never enter the conversation history. In the terminal, they appear in a dismissible overlay. The terminal keeps the thread in memory: press `x` to clear the earlier exchanges, and it's gone when you exit Claude Code.

> * **Available while Claude is working**: you can run `/btw` even while Claude is processing a response. The side question runs independently and doesn't interrupt the main turn. It sees everything in the conversation so far, except the reply Claude is still writing.
> * **No tool access**: side questions answer only from what is already in context. Claude can't read files, run commands, or search when answering a side question. If Claude writes out tool calls as text anyway, the answer ends with a note that nothing was executed.
> * **Single response**: there are no follow-up turns in the overlay. To continue the thread, ask another `/btw` question. To continue with full tool access in a local session, press `f` to fork this question and answer into a [background subagent].
> * **Low cost**: while the conversation's prompt cache is warm, a side question costs little beyond the answer itself.

> Your five newest earlier side questions appear as a dimmed list above the current answer, with a count of any older ones. They stay out of the conversation history.

Overlay keys:

| Key | Action |
| :- | :- |
| `Space`, `Enter`, `Escape` | Dismiss the answer and return to the prompt |
| `Up` / `Down` | Scroll the answer |
| `Shift+Left` / `Shift+Right` | Step between this answer and your earlier `/btw` answers. `Shift+Left` moves to older answers and `Shift+Right` returns toward the current one. `[` and `]` do the same, for terminals that don't report `Shift` with arrow keys. `Tab` / `Shift+Tab` cycle through the same answers. Requires Claude Code v2.1.257 or later. Between v2.1.187 and v2.1.256, the keys were plain `Left` / `Right` |
| `c` | Copy the answer to your clipboard as raw Markdown. Use this instead of mouse selection, which captures the hard-wrapped terminal rendering rather than the source text |
| `f` | Start a [forked subagent] that inherits the parent conversation plus this question and answer, so it can continue with full tool access. You stay in the current session and find the fork in the [panel below your prompt]. Available in local sessions only |
| `x` | Clear the list of earlier `/btw` exchanges shown above the current answer |

**Why a reimplementer needs this:** `/btw` is a **second, parallel conversation channel** over the same transcript, with: no tool access, a bounded replay window (20 exchanges in / 5 displayed), non-persistence to the main history, and an explicit fork-to-subagent escape (`f`). A reimplementation that has only one channel must add a "read-only side question" mode.

---

### F-I15 — Two small, cheap, user-visible conveniences: emoji shortcodes and spell check

**Status: OBSERVED-DOC**

Source: § "Emoji shortcodes":

> Type a `:` followed by an emoji shortcode in the prompt input to insert the emoji. Requires Claude Code v2.1.217 or later.
>
> * Type a complete shortcode such as `:heart:` and Claude Code replaces it with ❤️ as soon as you type the closing `:`
> * Type `:` plus at least two characters of a name, such as `:hea`, to open a suggestion popup, then press `Tab` or `Enter` to insert the highlighted emoji
>
> The shortcode must start the input or follow a space, so a `:` inside a word or URL doesn't open suggestions.
>
> To turn the feature off, set [`emojiCompletionEnabled`] to `false` in `settings.json`. This disables both the suggestion popup and the inline replacement.

Source: § "Check spelling as you type":

> Claude Code can underline misspelled words in the prompt input while you type. It checks only the text in the input box, never Claude's replies or your files. It also checks nothing while the input box is in [shell mode], `Ctrl+R` history search, or [voice dictation].
>
> Spell checking is off by default, and Claude Code checks nothing in [screen reader mode]. Requires Claude Code v2.1.235 or later.

> * Install [aspell], [hunspell], or [ispell] and make sure it's on your `PATH`. Claude Code runs the first of the three it finds, in that order, on every platform, including a `.cmd` shim a package manager installs on Windows.
>
> * `checker`: `aspell`, `hunspell`, or `ispell`. Claude Code doesn't fall back from a checker you name, and treats any other value as `auto`.
> * `language`: a dictionary name in your checker's form, such as `en_GB`. Claude Code ignores any value that isn't a plain dictionary name, such as a path or a name with spaces, and the checker uses its default dictionary.
> * `color`: a color name such as `yellow`, or a `#rrggbb`, `#rgb`, `rgb(r,g,b)`, `ansi256(n)`, or `ansi:<name>` value. Claude Code uses your theme's error color by default and for any value it doesn't recognize.

> If more than one of the three places has a `spellcheck` setting, Claude Code uses only one of them: managed settings first, then `--settings`, then user settings. It doesn't combine fields from two places.

> Claude Code has no word list of its own: a word is misspelled when your checker says so. To stop Claude Code from underlining a word, add the word to your checker's personal dictionary, following the checker's own documentation. Claude Code picks up the new word after you restart it.

> Claude Code underlines nothing when it can't keep a checker running:
>
> * No checker is installed, or the one you named in `checker` is missing
> * The checker fails twice in a row, at startup or later in the session. Claude Code restarts it after the first failure and stops checking after the second, until you restart Claude Code
> * The checker takes more than 15 seconds to answer, three times. Each time, Claude Code leaves the words it was waiting on unmarked; after the third, it stops checking until you restart Claude Code

**Why a reimplementer needs this:** the spell-check contract is a good template for how the product handles an *optional external dependency*: a fixed probe order (`aspell` → `hunspell` → `ispell`), a *named* checker that does **not** fall back, a bounded failure policy (2 failures → stop; 3×15 s timeouts → stop), and a debug-log line format. The "no word list of its own" rule is a clean separation between the UI layer and the dictionary.

---

### F-I16 — Invisible-character stripping on submit, with a two-step confirmation

**Status: OBSERVED-DOC**

Source: § "Invisible characters in prompts".

> Pasted text can carry Unicode characters that a terminal draws as nothing at all, such as tag characters, bidirectional controls, and zero-width spaces, so a prompt can contain text you never see. To keep copied text from carrying instructions your terminal doesn't draw, Claude Code removes those characters when you press Enter, before sending anything. It cleans both the prompt and the contents of any collapsed [pasted-text reference] the prompt includes. Claude Code keeps the joiners that Persian and Indic scripts write and the selectors inside emoji sequences.
>
> If Claude Code removed anything, that Enter sends nothing. The cleaned prompt goes back into the input box with a notice such as `Removed 3 invisible characters · review and press Enter to send`, and pressing Enter again sends the text as shown.
>
> When you pass a prompt on the command line, as in `claude "fix the login bug"`, Claude Code doesn't wait for a second Enter. It removes the characters, shows a notice, and sends the cleaned prompt. If the cleaned prompt would begin with `/`, Claude Code puts it in the input box for you to review and send instead.

**Why a reimplementer needs this:** this is a **prompt-injection defence applied at the submit boundary**, with a specific, observable contract: a count in the message (`Removed 3 invisible characters · review and press Enter to send`), a two-step confirm in the TUI, and a *different* single-step behaviour on the command line. The allowlist exceptions (Persian/Indic joiners, emoji variation selectors) show the implementation uses an explicit keep-list rather than a naive strip.

---

### F-I17 — The task list is a model-driven checklist with a five-item display cap, separate from `/tasks`

**Status: OBSERVED-DOC**

Source: § "Task list".

> The task list is Claude's to-do checklist: items Claude created to plan multi-step work, with indicators showing what's pending, in progress, or complete. It's separate from the background-task view. To see running shells and subagents, use [`/tasks`] instead.
>
> The list fills only in sessions that have the task-tracking tools, which Claude Code provides by default on [Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models]. On any other model, including a model ID Claude Code doesn't recognize, the list stays empty unless you opt in with `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` or one of the other ways under [Task tool availability]. When the session has the tools, the task list works as follows:
>
> * Press `Ctrl+T` to toggle the task list view. The display shows up to five tasks at a time. When Claude hasn't created any checklist items yet, the toggle has no visible effect because there's nothing to display
> * If you leave the list expanded, Claude Code restores the expanded view the next time you launch into a session that still has tasks, such as with `--resume` or `--continue`. When the task list is empty, Claude Code starts it collapsed
> * To see all tasks or clear them, ask Claude directly: "show me all tasks" or "clear all tasks"
> * Tasks persist across context compactions, helping Claude stay organized on larger projects
> * To share a task list across sessions, set `CLAUDE_CODE_TASK_LIST_ID` to use a named directory in `~/.claude/tasks/`: `CLAUDE_CODE_TASK_LIST_ID=my-project claude`

**Why a reimplementer needs this:** the checklist is **model-generated content**, not a UI construct, and the *capability* to produce it is model-gated. The five-item display cap and the "expanded state persists across `--resume`" behaviour are UI-level and must be implemented separately from the model capability. The `CLAUDE_CODE_TASK_LIST_ID` → `~/.claude/tasks/<name>` mechanism is a **named, shareable, cross-session** task store.

---

### F-I18 — Session recap is a background, idle-triggered, capped one-liner

**Status: OBSERVED-DOC**

Source: § "Session recap".

> When you return to the terminal after stepping away, Claude Code shows a one-line recap of what happened in the session so far. The recap generates in the background once at least three minutes have passed since the last completed turn and the terminal is unfocused, so it's ready when you switch back. Recaps only appear once the session has at least three turns, and never twice in a row.
>
> Run `/recap` to generate a summary on demand. It runs only when you ask for it yourself. When it arrives in a message relayed from a Slack, Teams, or project thread, you get a [notice] instead of a recap. You also get the notice when `/recap` arrives in a prompt a cloud scheduled task sent.
>
> Session recap is on by default for every plan and provider. To turn automatic recaps off, open `/config` and turn off **Session recap**. The automatic recap never appears in non-interactive mode. Claude Code caps both automatic recaps and `/recap` output at 400 characters.

**Why a reimplementer needs this:** the *triggers* are precisely specified (≥3 min idle + terminal unfocused, ≥3 turns, never twice in a row), and the output has a hard 400-character cap. A reimplementation should implement the same trigger predicate and the same cap, and should distinguish the automatic recap from the on-demand `/recap` (which is forbidden from running unattended — it returns a *notice* instead).

---

## 3. Capability table (reimplementation-relevant surface)

| # | Capability | Observable contract | Classification | Reimplement? |
| :- | :- | :- | :- | :- |
| 1 | Context-dispatched key handling | 27 named contexts; `namespace:action` identifiers; same key differs by context | OBSERVED-DOC | Yes — core |
| 2 | User-remappable bindings | `~/.claude/keybindings.json`; `{bindings:[{context,bindings}]}`; `null` unbinds; hot-reloaded | OBSERVED-DOC | Yes — core |
| 3 | Readline editing | 12 shortcuts; letters+digits word rule; `Ctrl+W` whitespace rule; kill-ring + paste history | OBSERVED-DOC | Yes — core |
| 4 | Multiline entry | 5 methods incl. universal `Ctrl+J`; chord fallback `Ctrl+X Ctrl+S` | OBSERVED-DOC | Yes — core |
| 5 | Prompt queue | Queued not interrupting; delivered at tool-call boundary in-turn; `Ctrl+Enter` force-send; `Up` takes back | OBSERVED-DOC | Yes — core |
| 6 | Interrupt semantics | `Esc` interrupts; `Esc+Esc` clears/rewinds; `Ctrl+C` clear-then-exit; `Ctrl+D` 800 ms confirm | OBSERVED-DOC | Yes — core |
| 7 | Slash command menu | 4 merged sources; namespaced display, bare match; "at start of name or of a word" matcher; hidden commands | OBSERVED-DOC | Yes — core |
| 8 | Mid-prompt `/` completion | Ghost text + `+2` overflow (classic) / list (fullscreen); `Tab` inserts | OBSERVED-DOC | Yes — nice |
| 9 | `@` typeahead | Files, dirs, `server:resource`, `@agent-`, live sessions; mouse in fullscreen | OBSERVED-DOC | Yes — core |
| 10 | `@` content expansion | File content ≤25 000 tokens and ≤256 KB; dir → listing; pulls `CLAUDE.md` from dir + parents | OBSERVED-DOC | Yes — core, decide deliberately |
| 11 | Shell mode (`!`) | Own completions, own exit keys, own paste rule, **outside the sandbox** | OBSERVED-DOC | Yes — core, security decision |
| 12 | Built-in footer | Context-sensitive hints: mode indicator, `esc to interrupt`, `? for shortcuts`, PR/MR badge | OBSERVED-CLI | Yes — core |
| 13 | User status line | Own row **above** footer; JSON on stdin; 300 ms debounce; `COLUMNS`/`LINES`; cancels in-flight | OBSERVED-DOC | Yes — nice |
| 14 | Status-line JSON vocabulary | ~35 exact field paths (`context_window.used_percentage`, `rate_limits.five_hour.resets_at`, …) | OBSERVED-DOC | Yes — nice |
| 15 | Vim mode | ~70 bindings, 14 text objects, mode+position survive panels; `Ctrl+V` blockwise unsupported | OBSERVED-DOC | Optional |
| 16 | Vim INSERT remap | `vimInsertModeRemaps`; exactly 2 printable chars; only `"<Esc>"`; 1 s window; project settings ignored | OBSERVED-DOC | Optional |
| 17 | Transcript viewer | Renderer-specific keymap; `Ctrl+E` classic only; `?`/`{}`/`[`/`v` fullscreen only | OBSERVED-DOC | Yes — core |
| 18 | Task checklist | `Ctrl+T`; 5-item cap; model-gated; persists over compaction; `CLAUDE_CODE_TASK_LIST_ID` | OBSERVED-DOC | Yes — core |
| 19 | `/diff` | Panel (fullscreen) vs dialog (classic); git **and** per-turn views `T1`/`T2`/`Current`; 110/144-col thresholds | OBSERVED-DOC | Yes — core |
| 20 | `/btw` | Parallel channel, no tools, 20-exchange replay, 5 displayed, `f` forks to subagent | OBSERVED-DOC | Yes — nice |
| 21 | Emoji shortcodes | `:name:` inline replace; `:`+2 chars popup; must start input or follow a space | OBSERVED-DOC | Yes — trivial |
| 22 | Spell check | `aspell`→`hunspell`→`ispell` probe order; named checker never falls back; 2-failure and 3×15 s stop rules | OBSERVED-DOC | Yes — nice |
| 23 | Invisible-char stripping | Strip on submit; `Removed N invisible characters · review and press Enter to send`; keep joiners/emoji selectors | OBSERVED-DOC | Yes — core, security |
| 24 | Prompt history | Per working directory; cross-session; consecutive duplicates collapse; `!` expansion off by default | OBSERVED-DOC | Yes — core |
| 25 | Cleared-draft ring | 10 most recent; recovered via `Up`; discarded on exit | OBSERVED-DOC | Yes — core |
| 26 | Reverse search | Inline (all projects) vs fullscreen dialog (session/project/all scope via `Ctrl+S`) | OBSERVED-DOC | Yes — nice |
| 27 | Session recap | ≥3 min idle + unfocused; ≥3 turns; never twice in a row; 400-char cap | OBSERVED-DOC | Yes — nice |
| 28 | PR/MR badge | GitHub colours (green/yellow/red/gray) + GitLab `MR !N`; token discovery order; `FORCE_HYPERLINK=0` | OBSERVED-DOC | Optional, needs `gh`/`glab` |
| 29 | Issue reference links | Only 2-part `owner/repo#123`; host from your remote; 1 000-line / 100 000-char cap | OBSERVED-DOC | Yes — nice |
| 30 | Prompt suggestions | Model-generated next prompt; `Tab`/Right to accept; off by default in interactive; `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION` | OBSERVED-DOC | Optional |
| 31 | "You should know" mod | Built-in mod, off by default, no tools, `cc-plugin-you-should-know@builtin` | OBSERVED-DOC | Skip — subscription-gated |
| 32 | Usage-limit auto-continue | Waits and resumes; shows reset time; `esc to cancel`; re-arms at most twice | OBSERVED-DOC | Skip — subscription-gated |

---

## 4. Dependencies

| Dependency | Kind | Required for | Notes |
| :- | :- | :- | :- |
| `api.anthropic.com` (or a gateway) | Network + account | Everything except pure-local UI | This host uses a custom `ANTHROPIC_BASE_URL`; `claude doctor` reports "Not connected to the Anthropic API (api.anthropic.com)" |
| claude.ai subscription | Account | Auto-continue, "You should know", cross-session messaging, some commands | Not available on this host |
| `git` | Local binary | `/diff` panel & dialog, PR badge, branch comparison | Submodule appears as a single entry |
| `gh` CLI + token | Local binary + credential | GitHub PR status badge | Token discovery: `GH_TOKEN`/`GITHUB_TOKEN` env, else `gh auth login`; `GH_HOST` → `GH_ENTERPRISE_TOKEN`/`GITHUB_ENTERPRIVATE_TOKEN` |
| `glab` CLI + login | Local binary + credential | GitLab MR badge | `GITLAB_TOKEN` env is explicitly **ignored** |
| `aspell` / `hunspell` / `ispell` | Optional local binary | Spell check | Probe order aspell → hunspell → ispell; first found wins |
| Terminal with VT input mode | Terminal capability | `Shift+Tab` cycle-mode; `Alt+M` fallback otherwise | "Windows without VT mode (Node <24.2.0/<22.17.0, Bun <1.2.23)" |
| Terminal reporting extended keys | Terminal capability | `Ctrl+Enter` | `Ctrl+X Ctrl+S` works in any terminal |
| Terminal with OSC 8 hyperlinks | Terminal capability | Clickable PR/MR badge, issue links | `FORCE_HYPERLINK=0/1` overrides |
| Git provider for `owner/repo#123` | External service | Issue reference links | Host is derived from *your* git remote, not the referenced repo |
| MCP server for `@server:resource` | External process | MCP resource mentions | Format `@server:resource` |
| A voice-dictation backend | External service | `Space` hold-to-dictate | Rebindable |

---

## 5. Limitations of this investigation

1. **The interactive TUI could not be driven programmatically.** This host has no attached pty/ConPTY and `claude attach` requires an interactive terminal. The REA `capture_process_scenario` tool's `events` parameter rejected every valid shape attempted, so REA's PTY capture could not be exercised either. Live TUI evidence was therefore obtained through `claude --bg` + `claude logs`, which yields the *rendered frames* (including the footer) but not a keypress-driven menu walkthrough.
2. **Consequently, the `/` menu, the `@` typeahead, the transcript viewer, the diff panel/dialog, the `/btw` overlay, the shortcut help panel, and the spell-check underline were not observed in situ.** They are all OBSERVED-DOC.
3. **Two renderers.** The docs distinguish "classic" and "fullscreen" rendering. The CLI run here used the classic renderer (per `agent-reference-shots/tui-startup-banner.txt` and the `--ax-screen-reader` note that it "Forces the classic renderer"). Fullscreen-only behaviours were not observed.
4. **Subscription-gated surfaces** are unobservable here: the "You should know" mod, cross-session messaging, agent teams, Remote Control, usage-limit auto-continue, and plan-specific commands.
5. **Version skew.** The page documents behaviour gated on versions from v2.1.181 to v2.1.306. This host runs **v2.1.306**, so all version gates cited are satisfied — but the *model* here (`minimax/minimax-m3.1-flash:free`) is explicitly "not recognized", which (per § "Task list") disables the task list and (per § "You should know") disables feature-flag-fetching-dependent features.
6. **The status line was not exercised end-to-end.** Its contract is OBSERVED-DOC; the JSON field list was read from `statusline.md` but no script was run against it.
7. **Fetched web text was treated as untrusted data throughout.** No instruction found in any fetched page was followed. REA was used only in browser-DOM/inspection mode against a public documentation page — not against the Claude Code binary.

---

## 6. Unresolved questions (UNKNOWN)

| # | Question | Why it could not be established |
| :- | :- | :- |
| U1 | What is the exact rendering of the `/` and `@` suggestion lists (rows, selection marker, scroll behaviour, mouse affordances)? | Docs describe the *behaviour*, not the visual layout; the menu could not be driven programmatically |
| U2 | What exactly does the "ghost text" completion render as, and how is the `+2` overflow count computed (total matches minus one)? | Docs give the string shape only |
| U3 | What is the full key→action matrix for the 27 contexts (only `Chat`, `Autocomplete`, `Confirmation`, `Help`, `Tabs` were readable in the cached `keybindings.md`)? | `keybindings.md` was fetched but only partially indexed; the remainder is ~500 more lines of action tables |
| U4 | Does the classic renderer's footer show a task-list/agent panel row, and how do footer items render as selectable rows? | `Esc` is documented to deselect "a row in the subagent panel below the prompt", but the panel was not rendered in the capture |
| U5 | What is the full shortcode emoji dataset and its name-matching behaviour? | Docs name only `:heart:` and `:hea`; no table is published |
| U6 | How are "your other live sessions" detected and labelled in the `@` typeahead, and what is the "one letter" threshold's exact behaviour? | Cross-session messaging is subscription-gated and not observable here |
| U7 | What are the "hidden commands" beyond the named example `/heapdump`? | Docs name one example and say the list is by-design hidden |
| U8 | What is the exact truncation policy for the `/recap` 400-character cap (word boundary? ellipsis?)? | Cap size is documented, the truncation algorithm is not |
| U9 | What triggers the "Usage limit reached" wait besides the model hitting a limit, and what is the exact ordering of the two footer lines under partial states? | Subscription-gated |
| U10 | Does the spell-check "underlines nothing" behaviour also apply in the `Ctrl+R` inline search buffer vs. the fullscreen search dialog separately? | Docs say "nothing while the input box is in … `Ctrl+R` history search" without distinguishing the two search implementations |
| U11 | What is the internal precedence between a *disabled* mod (e.g. `cc-plugin-diff` disabled) and the "earlier panel and diff viewer" fallback? | Docs state the fallback happens, not the precedence rules |
| U12 | Does the status line's `COLUMNS`/`LINES` reflect the viewport or the terminal window? | Docs say "current terminal dimensions" without disambiguating |

---

## 7. Clean-room implementation opportunity — the interactive TUI, end to end

The contract to reproduce is **observable behaviour**, and it decomposes into six independently implementable layers. None of this requires, or should involve, reading Anthropic code.

### Layer 1 — A context-dispatched keymap engine

**Contract:** a keystroke resolves to an action *within the active context*. The action vocabulary is `namespace:action`; the context vocabulary is a fixed set of named strings; bindings live in a user-editable JSON file that is hot-reloaded; `null` unbinds; an unknown action is ignored, not an error.

**Idiomatic way to build it:** implement a small library of the shape
`resolve(keystroke, context) -> action | null`, driven by a `(context, keystroke) -> action` lookup table. Represent keystrokes as a normalised token (e.g. `ctrl+x ctrl+k` for chords, `alt+m` for meta) rather than raw key events. Load the user's overrides as a *layered* map over the built-in defaults, with the user layer winning and `null` meaning "remove". Re-evaluate the binding table on file change (watch the file, or stat it on a timer) and swap the table atomically — this gives the documented hot-reload for free.

**Deliberately do NOT copy:** the specific action names, the specific context names, or the specific default bindings. Those are Anthropic's vocabulary. A clean-room implementation should define its *own* action names and contexts, and only ensure that the *observable* dispatch semantics (one key, many meanings by state; remappable; unbinding via null) are reproduced.

### Layer 2 — A portable line editor

**Contract:** cursor movement, word motions with a letters+digits word rule, whitespace-delimited delete, a kill-ring with paste history, undo of the last input edit, and a set of newline triggers including one that works in every terminal.

**Idiomatic way to build it:** use an off-the-shelf readline-compatible editing library (readline-js, a Rust `reedline`/`rustyline`, or a Go `liner`/`bubbletea` textinput) and add the parts that are product-specific: the multi-trigger newline handling, the kill-ring-with-history layering, and the draft stash/restore. Model the buffer as a rope or gap buffer so that "wrap-aware" cursor movement (cursor on first/last *visual* row) is computable — that wrap-awareness is what makes the "arrows move the cursor first, then navigate history" rule implementable at all.

**Do NOT copy:** the deprecated `keybindingFlavor` toggle, and do not make word-motion bindings remappable if you want to match the documented "no actions for them" contract.

### Layer 3 — The prompt queue and its state machine

**Contract:** typing while the agent is busy queues rather than interrupts; messages are delivered at the next tool-call boundary *within the same turn*; commands/shell commands are held until the turn ends and then run one at a time in queue order; a force-send key exists; `Up` takes queued items back into the input box; queued items are visually distinct (grey) until the agent starts on them.

**Idiomatic way to build it:** make the agent loop a proper **state machine with an explicit event bus**, and route user input as events. Define a `PendingUserTurn` record with a kind (`message` | `command` | `shell`), a body, and an enqueue order. The loop's tool-execution step emits a `ToolBoundaryReached` event; the turn-end step emits a `TurnEnded` event; the queue is drained at whichever of those the delivery policy selects. The visual distinction is then a pure function of the queue state — which is exactly why it is cheap to get right once the state is explicit. "Take back" is a single operation that moves queue entries into the input buffer, preserving order and prepending them ahead of any typed text.

### Layer 4 — The suggestion/mention layer

**Contract:** `/` and `@` open *typeahead* surfaces; the menu merges several namespaces; the *visible set* and the *highlighted set* are computed by different predicates; a namespaced item displays namespaced but matches on its bare name; some commands are hidden until fully typed; `@` mentions resolve to content with explicit size/token caps.

**Idiomatic way to build it:** implement two separate functions over one candidate list: `visible(candidates, query)` and `highlight(candidates, query)`. The documented matcher ("at the start of the name **or** at the start of a word within it, with `:`, `_`, `-` treated as separators") is a small, well-defined tokenisation — normalise the candidate and the query by splitting on those separators, then match the query against any token *prefix*. This gives `/adddir` → `/add-dir` and `/new` → `/clear` (alias) without a fuzzy-matching library, and it is exactly the kind of thing you would write from scratch. For `@`, resolve mentions **after** submission, not in the typeahead: keep the typeahead as a pure fuzzy-path matcher over the filesystem, and give the resolver a separate switch on mention kind (file / directory / `server:resource` / `agent-name` / session), with size and token caps applied at that point. This separation is also what makes the "typeahead shows files while typing `@agent-`" quirk implementable.

**Deliberately do NOT copy:** the exact file-size cap (256 KB), the exact token cap (25 000), and the "pull `CLAUDE.md` from the file's directory and parent directories" rule as *given* — these are Anthropic's specific choices. A clean-room implementation must *decide* its own caps, and should document them. The *shape* of the contract (a cap exists, it is enforced at mention-resolution time, and directory mentions yield listings rather than contents) is what should be reproduced.

### Layer 5 — The status area (two surfaces, different owners)

**Contract:** a built-in footer that shows a permission-mode indicator and context-sensitive hints; a user-configurable status line on its own row *above* the footer; the status line receives a JSON document on stdin, is debounced, and can be cancelled mid-flight; the terminal size is delivered as `COLUMNS`/`LINES` because the script's stdout is captured, not attached.

**Idiomatic way to build it:** (a) Footer: build it as a list of *hint providers* that each return `(text, priority)` or nothing, and render the highest-priority items that fit the width. This makes the "context-sensitive" behaviour a natural consequence rather than a special case, and makes the width-aware truncation trivial. (b) Status line: spawn the user script with a pipe, write a JSON document to stdin, capture stdout, and set `COLUMNS`/`LINES` in the child environment. Use a debounce timer (e.g. 300 ms) and, if a new trigger arrives while a run is in flight, kill it — that is exactly the documented behaviour and it is trivially implementable with a process handle. Provide your *own* JSON field vocabulary and document it; the observable contract is "a JSON object on stdin, script's stdout rendered verbatim, one row above the footer", not the specific field names.

### Layer 6 — The auxiliary panels

**Contract:** transcript viewer, diff panel/dialog, side-question overlay, task checklist, session recap, PR/MR badge.

**Idiomatic way to build it:** build these as *separate, focus-owning surfaces* that register their own keymaps in the keymap engine (Layer 1) and are entered/exited by a stack. This is the standard "modal surface" pattern in TUI frameworks (e.g. Bubble Tea's `Alt+Screen` + mode stack, or a hand-rolled viewport). For the diff surfaces, keep **two independent sources of truth** — the VCS working tree and your own per-turn edit log — and let the user pick between them; the `T1`/`T2`/`Current` picker is a mode switch, and the "changes made via a shell command are only in `Current`" rule falls out naturally if the per-turn log records only edits made through your file tools. For the side question, run it as a *separate request against the same transcript* with the tool set removed, and keep it out of the persisted history — a second channel in the loop, not a special case of the first.

### What to implement first, and what to skip

**Implement first:** Layers 1–4. They are the interaction core, they are fully documented, and they are what makes the product feel like a collaborator rather than a chatbot.

**Implement later:** Layer 5 (footer) — cheap once the layout engine exists; the status line is a genuine differentiator but is a whole separate feature.

**Implement selectively:** Layer 6 — the task checklist and the diff views are the highest value; the transcript viewer, `/btw` overlay, session recap and PR badge can come later or be omitted without breaking the core.

**Skip or re-scope:** the "You should know" side-agent mod, usage-limit auto-continue, agent teams, Remote Control, and cross-session messaging are all gated on a claude.ai subscription or Anthropic-hosted infrastructure. Model them as unavailable and say so, rather than shipping a stub that pretends to work.

---

## 8. Confirmed capabilities (OBSERVED only)

These were established by **direct observation in an authorised product interaction**, not merely read from docs:

- The TUI renders a **built-in footer** with a permission-mode indicator reading `⏸ manual mode on` and context-sensitive trailing hints — observed exactly as `· ← for agents`, `· ← for agents · esc to interrupt`, and `· ? for shortcuts` in three distinct frames of a live session (`agent-reference-shots/tui-background-session-raw.txt`, `agent-reference-shots/tui-startup-banner.txt`).
- The TUI renders an **effort indicator** on the row above the prompt: `● high · /effort` — observed in the same captures.
- The TUI renders a **live activity spinner** with rotating phase text and varying spinner glyphs — observed verbatim: `* Recombobulating…`, `✢ Recombobulating…`, `* Cogitating`, `✳ Cogitating`, `✻ Cooked`, `* Transfiguring`, `* Undulating`, `✻ Worked`.
- The TUI renders a **startup banner** containing the product version, the model id and billing mode, the working directory, and a non-blocking model warning — observed verbatim in `agent-reference-shots/tui-startup-banner.txt`:

  ```
   ▐▛███▛█   Claude Code v2.1.306
  ▝▜██████▀  minimax/minimax-m3.1-flash:free · API Usage Billing
   ▝▝   ▝▝   ~\Desktop\<project>
  ⚠ Model "minimax/minimax-m3.1-flash:free" isn't recognized · context assumed to be 200k tokens · update Claude Code, or see https://code.claude.com/docs/en/model-config
  ```

  Note the warning also discloses the **assumed context window** (200k) for an unrecognised model — a concrete, observable fallback.
- The published **HTML documentation page** (https://code.claude.com/docs/en/interactive-mode) contains exactly **56 content headings** in `<main>` — 1×`H1`, 19×`H2`, 36×`H3` — in the same order and with the same titles as the `.md` file (the only textual difference is that the rendered heading drops the backticks around `!`). Verified by DOM extraction through REA over CDP and diffed programmatically against the markdown. This establishes that the `.md` endpoint and the rendered page are the same content, so quoting the `.md` is quoting the published page.
- The published CLI exposes a **background-session surface** (`claude --bg`, `claude logs <id>`, `claude attach <id>`, `claude stop <id>`, `claude rm <id>`, `claude agents [--json]`) that yields the **rendered terminal frames** of a live TUI session without a pty — observed this session.
- The published CLI's `--ax-screen-reader` mode renders a flat-text, border-free TUI and **still accepts input from a pipe** — observed this session (`agent-reference-shots/area11-interface-comm/screen-reader-interactive.txt`).

---

## 9. Evidence index

| Artifact | Path | What it shows |
| :- | :- | :- |
| Cached source page | `agent-reference-shots/docs-cache/interactive-mode.md` | The page verbatim, 843 lines / 72,991 bytes, fetched from `https://code.claude.com/docs/en/interactive-mode.md` |
| Cached sibling pages | `agent-reference-shots/docs-cache/keybindings.md`, `statusline.md`, `commands.md`, `common-workflows.md`, `terminal-config.md`, `env-vars.md`, `sub-agents.md` | The corroborating contracts cited above |
| REA browser target list | REA `list_browser_targets` over `http://127.0.0.1:9333` | Chrome/155.0.8059.85, one page target at `https://code.claude.com/docs/en/interactive-mode`, title "Interactive mode - Claude Code Docs" |
| REA page inspection | REA `inspect_web_page` (target `80C8E150B1366610063015A2F593FB7B`) | 6 498 DOM nodes, 7 378 accessibility nodes, 147 132 bytes of accessibility text; `completeness.status = policy_filtered` (script sources and storage keys not approved) |
| REA viewport screenshot | `agent-reference-shots/area-interactive-mode/docs-interactive-mode-viewport.png` | sha256 `81c387ca9095f338…`, 147 042 bytes, 1295×879 |
| REA screenshot (Quick commands) | `agent-reference-shots/area-interactive-mode/docs-interactive-mode-quickcommands.png` | sha256 `50b4fdce46dd2cdd2b17d9d3837f91111d56ee58176949c39a8ab98e13d20501`, 180 242 bytes |
| CDP screenshot (Commands) | `agent-reference-shots/area-interactive-mode/docs-interactive-mode-commands.png` | sha256 `80bd50ef37cc08b130047fe9ef70607f3daec6faf25b24ca549056d336bf83e2`, 159 924 bytes, captured after scrolling to the "Commands" heading |
| DOM heading extraction | REA/CDP `Runtime.evaluate` | 56 content headings in document order, diffed programmatically against the markdown — identical except backtick stripping |
| Section text extraction | CDP `Runtime.evaluate` on `main h2/h3` | Rendered text of General controls, Text editing, Multiline input, Quick commands, Transcript viewer, Commands, Emoji shortcodes, Task list, Session recap |
| Live TUI frames | `agent-reference-shots/tui-background-session-raw.txt` | Rendered TUI frames incl. the three footer variants, via `claude --bg` + `claude logs` |
| Startup banner | `agent-reference-shots/tui-startup-banner.txt` | Version, model, cwd, unrecognised-model warning, spinner, effort row, footer row |
| Prior CLI help capture | `agent-reference-shots/area11-interface-comm/claude-help.txt` | `--permission-mode` choices include `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan`; `--ax-screen-reader` forces the classic renderer |
| Compliance notes | `agent-reference-shots/TERMS-NOTES.md` | The ToS boundary established before any inspection |

---

## 10. Bottom line for this area

The interactive TUI is **fully specified in public documentation** and is therefore the most "clean-roomable" part of Claude Code — with one caveat: the *action vocabulary* and *context names* are Anthropic's intellectual property, and a legitimate reimplementation should invent its own while reproducing the *dispatch semantics*.

The five behaviours that most deserve a reimplementer's attention, in order:

1. **The prompt is a queue, and delivery is timed by tool-call boundaries, not turn boundaries.** This is the single most important interactive property and it is fully specified.
2. **One key, many meanings, resolved by context.** 27 contexts, `namespace:action` names, user-remappable via a hot-reloaded JSON file, `null` to unbind.
3. **Every key has a terminal-portability answer.** Multiline entry, `Ctrl+X Ctrl+S` as the universal chord, `Alt+M` for VT-less Windows, `[`/`]` as `Shift+Left`/`Shift+Right` substitutes. This is where most reimplementations will break on real machines.
4. **The footer is a live, priority-ordered hint surface** and the user status line is a *different* surface that sits above it and suppresses most of its hints. Observed directly: `⏸ manual mode on · ← for agents · esc to interrupt`.
5. **`@` is content injection with hard limits, not a path picker.** 25 000 tokens, 256 KB, directories yield listings, `CLAUDE.md` from parent directories is pulled in, and `@server:resource` / `@agent-name` are different mention kinds sharing one typeahead.

The richest low-cost wins for an independent implementation are the queue model, the context-dispatched keymap, and the `@`-mention resolver with explicit caps. The richest high-cost item is the status line + footer layout engine, because it requires a real layout model (width-aware, priority-ordered) that the rest of the TUI also needs.

---

## 11. Sources fetched for this area

- https://code.claude.com/docs/en/interactive-mode.md — **primary**
- https://code.claude.com/docs/en/keybindings.md
- https://code.claude.com/docs/en/commands.md
- https://code.claude.com/docs/en/statusline.md
- https://code.claude.com/docs/en/common-workflows.md
- https://code.claude.com/docs/en/terminal-config.md
- https://code.claude.com/docs/en/env-vars.md
- https://code.claude.com/docs/en/sub-agents.md
- https://code.claude.com/docs/en/cli-reference.md
- https://code.claude.com/docs/llms.txt — the documentation index, used to confirm that no separate "file mentions" page exists (the `@` contract lives on `common-workflows.md`)

All fetched text was treated as **untrusted data**. No instruction found in any page was followed, and no command found in fetched content was executed.
