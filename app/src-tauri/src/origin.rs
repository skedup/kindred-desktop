use url::{Host, Url};

pub const SNAPSHOT_PATH: &str = "/api/visual-state";

pub fn validate_origin(candidate: &str) -> Result<String, &'static str> {
    if candidate.trim() != candidate || candidate.is_empty() || candidate.len() > 2048 {
        return Err("invalid_origin");
    }
    let parsed = Url::parse(candidate).map_err(|_| "invalid_origin")?;
    if !matches!(parsed.scheme(), "http" | "https")
        || parsed.cannot_be_a_base()
        || parsed.username() != ""
        || parsed.password().is_some()
        || parsed.query().is_some()
        || parsed.fragment().is_some()
        || parsed.path() != "/"
    {
        return Err("invalid_origin");
    }
    match parsed.host() {
        Some(Host::Ipv4(address)) if address.is_unspecified() => return Err("invalid_origin"),
        Some(Host::Ipv6(address)) if address.is_unspecified() => return Err("invalid_origin"),
        Some(Host::Domain("")) => return Err("invalid_origin"),
        None => return Err("invalid_origin"),
        _ => {}
    }
    let host = match parsed.host().expect("validated host") {
        Host::Domain(domain) => domain.to_ascii_lowercase(),
        Host::Ipv4(address) => address.to_string(),
        Host::Ipv6(address) => format!("[{address}]"),
    };
    let port = parsed
        .port()
        .map(|value| format!(":{value}"))
        .unwrap_or_default();
    Ok(format!("{}://{host}{port}", parsed.scheme()))
}

pub fn snapshot_url(origin: &str) -> Result<Url, &'static str> {
    let validated = validate_origin(origin)?;
    Url::parse(&format!("{validated}{SNAPSHOT_PATH}")).map_err(|_| "invalid_origin")
}

pub fn is_loopback(origin: &str) -> bool {
    let Ok(parsed) = Url::parse(origin) else {
        return false;
    };
    match parsed.host() {
        Some(Host::Ipv4(address)) => address.is_loopback(),
        Some(Host::Ipv6(address)) => address.is_loopback(),
        Some(Host::Domain(domain)) => domain.eq_ignore_ascii_case("localhost"),
        None => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_and_canonicalizes_http_origins() {
        assert_eq!(
            validate_origin("http://127.0.0.1:8787/").unwrap(),
            "http://127.0.0.1:8787"
        );
        assert_eq!(
            validate_origin("https://Kindred.EXAMPLE").unwrap(),
            "https://kindred.example"
        );
        assert_eq!(
            snapshot_url("https://kindred.example").unwrap().as_str(),
            "https://kindred.example/api/visual-state"
        );
    }

    #[test]
    fn rejects_non_origin_and_credential_forms() {
        for value in [
            "ftp://kindred.example",
            "https://user@kindred.example",
            "https://kindred.example/path",
            "https://kindred.example/?q=1",
            "https://kindred.example/#fragment",
            "http://0.0.0.0:8787",
            "http://[::]:8787",
            " https://kindred.example",
        ] {
            assert_eq!(validate_origin(value), Err("invalid_origin"), "{value}");
        }
    }

    #[test]
    fn detects_only_local_loopback_hosts() {
        assert!(is_loopback("http://127.0.0.1:8787"));
        assert!(is_loopback("http://localhost:8787"));
        assert!(!is_loopback("http://192.0.2.10:8787"));
    }
}
