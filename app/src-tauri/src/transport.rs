use crate::origin::snapshot_url;
use reqwest::{header, redirect::Policy, Client, StatusCode};
use serde::Serialize;
use serde_json::Value;
use std::time::Duration;

const MAX_SNAPSHOT_BYTES: usize = 16 * 1024;

#[derive(Clone, Debug, Serialize)]
pub struct SnapshotEnvelope {
    pub snapshot: Value,
    pub observation_generation: u64,
    pub source_label: String,
}

pub fn build_client() -> Result<Client, String> {
    build_client_with_timeouts(Duration::from_secs(2), Duration::from_secs(5))
}

fn build_client_with_timeouts(
    connect_timeout: Duration,
    total_timeout: Duration,
) -> Result<Client, String> {
    Client::builder()
        .redirect(Policy::none())
        .connect_timeout(connect_timeout)
        .timeout(total_timeout)
        .user_agent("kindred-desktop-spirit/0.1")
        .build()
        .map_err(|_| "snapshot_client_failed".to_owned())
}

pub async fn fetch(client: &Client, origin: &str) -> Result<Value, String> {
    let url = snapshot_url(origin).map_err(str::to_owned)?;
    let mut response = client
        .get(url)
        .header(header::ACCEPT, "application/json")
        .send()
        .await
        .map_err(|_| "snapshot_transport_failed".to_owned())?;
    if response.status() != StatusCode::OK {
        return Err(if response.status().is_redirection() {
            "snapshot_redirect_rejected".to_owned()
        } else {
            "snapshot_status_rejected".to_owned()
        });
    }
    let content_type = response
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.split(';').next())
        .map(str::trim);
    if content_type != Some("application/json") {
        return Err("snapshot_content_type_rejected".to_owned());
    }
    if response
        .content_length()
        .is_some_and(|length| length > MAX_SNAPSHOT_BYTES as u64)
    {
        return Err("snapshot_too_large".to_owned());
    }
    let mut bytes = Vec::with_capacity(2048);
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "snapshot_transport_failed".to_owned())?
    {
        if bytes.len().saturating_add(chunk.len()) > MAX_SNAPSHOT_BYTES {
            return Err("snapshot_too_large".to_owned());
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes).map_err(|_| "snapshot_json_invalid".to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{Read, Write},
        net::TcpListener,
        sync::mpsc::{self, Receiver},
        thread,
    };

    fn serve_once(response: Vec<u8>, delay: Duration) -> (String, Receiver<String>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(1)))
                .unwrap();
            let mut request = Vec::new();
            let mut buffer = [0_u8; 1024];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let read = stream.read(&mut buffer).unwrap_or(0);
                if read == 0 {
                    break;
                }
                request.extend_from_slice(&buffer[..read]);
            }
            let _ = sender.send(String::from_utf8_lossy(&request).into_owned());
            thread::sleep(delay);
            let _ = stream.write_all(&response);
        });
        (format!("http://{address}"), receiver)
    }

    fn response(status: &str, content_type: &str, body: &[u8]) -> Vec<u8> {
        format!(
            "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        )
        .into_bytes()
        .into_iter()
        .chain(body.iter().copied())
        .collect()
    }

    #[test]
    fn host_limits_are_intentionally_small_and_fixed() {
        assert_eq!(MAX_SNAPSHOT_BYTES, 16_384);
        assert!(build_client().is_ok());
    }

    #[tokio::test]
    async fn fetches_only_the_fixed_plain_get_without_credentials() {
        let body = br#"{"schema_version":1,"source_id":"fixture","status":"empty"}"#;
        let (origin, request) = serve_once(
            response("200 OK", "application/json; charset=utf-8", body),
            Duration::ZERO,
        );
        let value = fetch(&build_client().unwrap(), &origin).await.unwrap();
        assert_eq!(value["status"], "empty");
        let request = request.recv_timeout(Duration::from_secs(1)).unwrap();
        assert!(request.starts_with("GET /api/visual-state HTTP/1.1\r\n"));
        assert!(request
            .to_ascii_lowercase()
            .contains("accept: application/json"));
        assert!(!request.to_ascii_lowercase().contains("authorization:"));
        assert!(!request.to_ascii_lowercase().contains("cookie:"));
    }

    #[tokio::test]
    async fn rejects_redirects_content_types_and_oversized_bodies() {
        let cases = [
            (
                response("302 Found", "application/json", b"{}"),
                "snapshot_redirect_rejected",
            ),
            (
                response("200 OK", "text/html", b"{}"),
                "snapshot_content_type_rejected",
            ),
            (
                response(
                    "200 OK",
                    "application/json",
                    &vec![b' '; MAX_SNAPSHOT_BYTES + 1],
                ),
                "snapshot_too_large",
            ),
        ];
        for (wire_response, expected) in cases {
            let (origin, _) = serve_once(wire_response, Duration::ZERO);
            assert_eq!(
                fetch(&build_client().unwrap(), &origin).await,
                Err(expected.into())
            );
        }
    }

    #[tokio::test]
    async fn total_timeout_cancels_a_slow_snapshot() {
        let (origin, _) = serve_once(
            response("200 OK", "application/json", b"{}"),
            Duration::from_millis(150),
        );
        let client =
            build_client_with_timeouts(Duration::from_millis(30), Duration::from_millis(30))
                .unwrap();
        assert_eq!(
            fetch(&client, &origin).await,
            Err("snapshot_transport_failed".into())
        );
    }
}
