//! Keel desktop shell — a thin stdio IPC layer over the keel CLI.
//!
//! Sends `keel -p <prompt> --provider <p> --permission-mode <m> [--i-accept-the-risk]
//! --output-format stream-json` and re-emits each NDJSON line to the frontend as
//! the `keel:event` Tauri event. No agent logic lives here — the harness does
//! the work, this window is just a very nice terminal.

#![cfg_attr(mobile, allow(dead_code))]

use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};

use serde::Deserialize;
use tauri::{AppHandle, Emitter};

#[derive(Debug, Deserialize)]
#[serde(default)]
struct SendRequest {
    prompt: String,
    provider: String,
    permission_mode: String,
    accept_risk: bool,
}

impl Default for SendRequest {
    fn default() -> Self {
        Self {
            prompt: String::new(),
            provider: "auto".to_string(),
            permission_mode: "default".to_string(),
            accept_risk: false,
        }
    }
}

#[tauri::command]
async fn keel_send(app: AppHandle, request: SendRequest) -> Result<String, String> {
    if request.prompt.trim().is_empty() {
        return Err("prompt must not be empty".to_string());
    }

    let keel_bin = std::env::var("KEEL_BIN").unwrap_or_else(|_| "keel".to_string());
    let mut command = Command::new(&keel_bin);
    command
        .arg("-p")
        .arg(&request.prompt)
        .arg("--provider")
        .arg(&request.provider)
        .arg("--permission-mode")
        .arg(&request.permission_mode)
        .arg("--output-format")
        .arg("stream-json")
        .arg("--seed")
        .arg("0")
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());

    if request.permission_mode == "bypassPermissions" {
        if !request.accept_risk {
            return Err("bypassPermissions requires explicit risk acceptance".to_string());
        }
        command.arg("--i-accept-the-risk");
    }

    let mut child = command.spawn().map_err(|error| {
        format!(
            "failed to spawn {keel_bin}: {error}. Is keel installed and on PATH? \
             Try `pip install -e keel` or set KEEL_BIN."
        )
    })?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "keel stdout was not piped".to_string())?;

    let app_for_thread = app.clone();
    std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines().map_while(Result::ok) {
            if line.trim().is_empty() {
                continue;
            }
            // forward the raw line; the frontend parses it as stream-json
            let _ = app_for_thread.emit("keel:event", line);
        }
        let _ = child.wait();
        let _ = app_for_thread.emit("keel:done", ());
    });

    Ok("started".to_string())
}

#[tauri::command]
fn keel_version() -> Result<String, String> {
    let output = Command::new(
        std::env::var("KEEL_BIN").unwrap_or_else(|_| "keel".to_string()),
    )
    .arg("--version")
    .output()
    .map_err(|error| format!("keel --version failed: {error}"))?;
    let version = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if version.is_empty() {
        return Err("keel produced no version output".to_string());
    }
    Ok(version)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![keel_send, keel_version])
        .run(tauri::generate_context!())
        .expect("error while running keel desktop");
}

fn main() {
    run();
}
