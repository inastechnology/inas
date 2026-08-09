# Local Hub Self-Healing Healthcheck

## Purpose

Local Hubの`/readyz`、MQTT、Cloudflare Tunnel、Wi-Fi経路、DNS、登録カメラを定期確認し、連続失敗時に対象サービスまたはネットワークを段階的に復旧するsystemd healthcheckを追加する。障害と復旧はDiscordへ通知し、ネットワーク断中に送れなかった通知は復旧後に要約して送る。

## Progress

- [x] 既存のHub health API、systemd構成、Discord設定、障害ログを確認した。
- [x] healthcheck実装とfocused testsを追加する。
- [x] systemd service/timerとinstall_serviceへの導入処理を追加する。
- [x] 永続journal、Wi-Fi省電力無効化、Waitress設定を導入する。
- [x] 仮想APを停止し、実機で復旧判定と通知を検証する。
- [x] 重要異常3回でhost再起動、起動通知、6時間heartbeat、起動猶予を実運用設定へ反映する。
- [x] 2回の制御再起動でOS、Wi-Fi、Hub、MQTT、Tunnel、timer、Discord起動確認の自動復旧を検証する。

## Decisions

- Hub自体は公開済みの`/readyz`をlocalhostから確認する。認証済み管理APIや秘密情報には依存しない。
- 元障害を検知できるよう、Hub readinessとは別にgateway、DNS/TCP、Cloudflare Tunnel readiness、登録カメラのTCP到達性を確認する。
- 一時障害でサービスを揺らさないよう、連続失敗回数とaction cooldownを永続stateへ保存する。
- Hub異常はHub再起動、MQTT異常はMosquittoとHub再起動、Tunnel異常はTunnel再起動、ネットワーク異常はWi-Fi再接続、NetworkManager再起動、設定時のみhost再起動の順で復旧する。
- カメラ単独障害はHubやWi-Fiを無条件再起動せず通知する。ネットワーク障害を伴う場合はネットワーク復旧に含める。
- Discord送信不能時はstateへ障害を保持し、接続回復後に障害期間と実施actionを通知する。
- journal永続化はdrop-inとして導入し、削除すればRaspberry Pi OS既定のvolatile設定へ戻せるようにする。
- 実運用ではHub、MQTT、network、Tunnelの3回連続失敗でhostを再起動する。再起動cooldownは6時間とし、camera単独異常による再起動loopは避ける。
- 起動直後10分は異常回数を増やさず、遅い初期化をhangと誤認しない。起動確認と6時間ごとの正常heartbeatをDiscordへ送る。
- Tursoは600秒間隔のbackground syncを利用し、書き込みごとの明示syncは無効化する。remote sync遅延でLocal HubのHTTP起動やlocal書き込みを止めない。

## Validation

healthcheckの判定・連続失敗・復旧action・Discord保留通知のfocused tests、Ruff、既存web security testsを実行する。実機導入後は`/healthz`と`/readyz`、Waitress、healthcheck timer、永続journal、Wi-Fi power-save、仮想AP停止、Cloudflare Tunnel、Discord test notificationを確認する。

実施結果: focused testsとRuff全体checkは成功。全453 testsでは今回追加したconfiguration catalogの失敗を修正後、日付に依存する既存のplant calendar tests 3件のみが残る。最初の制御再起動でTurso明示sync待ちと起動猶予不足を検出して修正。2回目の制御再起動では追加操作なしでHubが約86秒で起動し、timerはboot_grace中に全5項目ok、boot ID更新とDiscord起動確認stateを記録した。systemdのhardware watchdogはruntime 1分、reboot 2分。制限されたhealthcheck unitからの`systemctl --dry-run reboot`も成功した。
