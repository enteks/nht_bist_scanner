[app]

# Uygulama başlığı
title = NhT BIST Scanner

# Paket adı (küçük harf, nokta yok)
package.name = nhtbistscanner

# Paket domain
package.domain = org.nhtbist

# Ana Python dosyası
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

# Versiyon
version = 1.0

# Gereksinimler
requirements = python3,kivy==2.3.0,pandas,numpy,yfinance,requests,urllib3,certifi,charset-normalizer,idna,multitasking,peewee,frozendict,lxml,html5lib,webencodings,beautifulsoup4

# Ekran yönü
orientation = portrait

# Android izinleri
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# Android API versiyonları
android.minapi = 21
android.api = 33
android.ndk = 25b
android.sdk = 33

# NDK path (GitHub Actions otomatik ayarlar)
# android.ndk_path =
# android.sdk_path =

# Mimari
android.archs = arm64-v8a, armeabi-v7a

# Uygulama ikonu (opsiyonel)
# icon.filename = %(source.dir)s/data/icon.png

# Log level
log_level = 2

# Fullscreen
fullscreen = 0

[buildozer]

# Buildozer log level
log_level = 2

# Warn on root (GitHub Actions için 0 yap)
warn_on_root = 1
