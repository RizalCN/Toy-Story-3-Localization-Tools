[app]
title = Toy Story 3 Safe Translator
package.name = safetranslator
package.domain = org.rizalcn
source.dir = .
source.include_exts = py,txt,md
version = 1.0.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 23
android.target_sdk = 28
android.ndk = 25b
# Pin Python-for-Android: master pulled CPython 3.14.2, which fails on Android API 23
p4a.branch = v2024.01.21
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = False

[buildozer]
log_level = 2
warn_on_root = 1
