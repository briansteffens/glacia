class python3 {
  package { ["python3", "libpython3-dev", "python3-pip"]:
    ensure  => present,
    require => Class["squid-proxy"],
  }
}
