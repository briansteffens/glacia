class squid-proxy {
  package { "squid-deb-proxy-client":
    ensure  => present,
    require => Class["system-update"],
  }
}
