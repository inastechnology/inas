---
title: Raspberry Piを準備する
description: Raspberry Pi OS、hostname、mDNS、固定IP、Mosquittoを準備してHubを導入できる状態にします。
---

このページのコマンドは、すべて **Hubとして使うRaspberry Pi上** で実行します。機器がまだない場合は、先に[機器を選んで購入する](/start/hardware/)へ戻ってください。

## 1. Raspberry Pi OSを書き込む

別のPCでRaspberry Pi Imagerを使い、**Raspberry Pi OS Lite 64-bit** の最新安定版を書き込みます。Imagerの事前設定で次を指定します。

- [ ] 固有のhostname。例: `farm-a01`
- [ ] 管理用usernameと強いpassword、またはSSH公開鍵
- [ ] timezoneとkeyboard layout
- [ ] Wi‑Fiを使う場合だけSSID、password、国コード
- [ ] SSHを有効化

同じLANで同じhostnameを重複させないでください。Hubは画面なしで常時稼働させるため、Desktop版ではなくLite版を推奨します。

## 2. 起動してOSを更新する

Raspberry Piを有線LANへ接続して起動し、別PCからSSHで入ります。

```bash
ssh <ユーザー名>@farm-a01.local
sudo apt update
sudo apt full-upgrade
sudo reboot
```

再起動後にもう一度SSH接続します。

## 3. hostnameとmDNSを確認する

```bash
hostnamectl
getent hosts farm-a01.local
```

変更が必要な場合は次を実行し、再起動します。`farm-a01`は自分で決めた値へ置き換えます。

```bash
sudo hostnamectl set-hostname farm-a01
sudo reboot
```

Raspberry Pi OSではAvahiがhostnameに`.local`を付けたmDNS名を提供します。別PCから`ping farm-a01.local`または`ssh`で到達できることを確認します。

## 4. DHCP予約を設定する

ルーターの管理画面で、Raspberry PiのEthernet MAC addressへ同じIPを割り当てるDHCP予約を作ります。OSへ手入力する固定IPより、ルーター側の予約を推奨します。

```bash
ip link show eth0
hostname -I
```

予約後に再起動し、同じIPとmDNS名で到達できることを確認します。

## 5. OSパッケージを入れる

```bash
sudo apt install git curl mosquitto mosquitto-clients avahi-daemon ffmpeg
sudo systemctl enable --now avahi-daemon
```

Python依存関係は`uv`で管理します。[uv公式インストール手順](https://docs.astral.sh/uv/getting-started/installation/)に従って、Hubを動かす一般ユーザーへインストールしてください。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

一度logout/loginし、確認します。

```bash
uv --version
git --version
ffmpeg -version
```

## 6. MQTT brokerを設定する

デバイスとHubが接続するMosquittoを、同じRaspberry Piで動かします。まずpasswordを作成します。

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd inas-device
sudo chown root:mosquitto /etc/mosquitto/passwd
sudo chmod 640 /etc/mosquitto/passwd
```

`/etc/mosquitto/conf.d/inas.conf`をroot権限で作成し、次を保存します。

```text
listener 1883 0.0.0.0
allow_anonymous false
password_file /etc/mosquitto/passwd

connection_messages true
log_dest topic
```

```bash
sudo systemctl enable --now mosquitto
sudo systemctl restart mosquitto
systemctl status mosquitto --no-pager
```

passwordをshell historyへ書かず、2つのterminalからpublish/subscribeを確認します。

それぞれのterminalでpasswordを非表示入力してから実行します。passwordの文字列自体はshell historyへ残りません。

```bash
read -rsp 'MQTT password: ' MQTT_TEST_PASSWORD
mosquitto_sub -h localhost -p 1883 -u inas-device -P "$MQTT_TEST_PASSWORD" -t 'inas/setup-test'
```

```bash
read -rsp 'MQTT password: ' MQTT_TEST_PASSWORD
mosquitto_pub -h localhost -p 1883 -u inas-device -P "$MQTT_TEST_PASSWORD" -t 'inas/setup-test' -m 'ok'
unset MQTT_TEST_PASSWORD
```

確認後、MQTT username/passwordをpassword managerへ保存します。同じ値をHubの`.env`と各デバイスのsetup APへ入力します。

:::danger[MQTTをInternetへ公開しない]
ルーターでTCP 1883をport forwardしないでください。MQTTは平文TCPのため、信頼できる圃場LANだけから到達可能にします。
:::

## 完了条件

- Raspberry Piへ`<hub名>.local`でSSH接続でき、DHCP予約IPを記録済み
- DHCP予約後もIPが変わらない
- `uv`、`git`、`ffmpeg`を実行できる
- Mosquittoが`active (running)`で、認証付きpublish/subscribeに成功する
- ルーターに1883・39151のInternet向けport forwardがない

ここまで終わったら[Hubをインストール](/hub/install/)へ進みます。
