import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://docs.inas-technologies.com",
  integrations: [
    starlight({
      title: "INAS Documentation",
      description: "INAS Hubとデバイスを、セットアップから日々の運用まで迷わず使うための公式ドキュメント。",
      logo: {
        src: "./src/assets/inas-docs-logo.svg",
        alt: "INAS Documentation",
        replacesTitle: true,
      },
      favicon: "/favicon.svg",
      customCss: ["./src/styles/custom.css"],
      defaultLocale: "root",
      locales: {
        root: { label: "日本語", lang: "ja" },
      },
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/inastechnology/inas" },
      ],
      editLink: {
        baseUrl: "https://github.com/inastechnology/inas/edit/main/docs-site/",
      },
      lastUpdated: true,
      pagination: true,
      tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 3 },
      sidebar: [
        {
          label: "はじめる",
          items: [
            { label: "全体構成を理解する", slug: "start/overview" },
            { label: "導入ルートを選ぶ", slug: "start/choose-path" },
            { label: "機器を選んで購入", slug: "start/hardware" },
            { label: "購入前チェック", slug: "start/prerequisites" },
            { label: "ネットワークを決める", slug: "start/network" },
            { label: "安全上の注意", slug: "start/safety" },
            { label: "自己調達の全手順", slug: "start/quickstart" },
            { label: "弊社提供機器（準備中）", slug: "start/provided-hardware" },
          ],
        },
        {
          label: "Hubをセットアップ",
          items: [
            { label: "Raspberry Piを準備", slug: "hub/raspberry-pi" },
            { label: "Hubをインストール", slug: "hub/install" },
            { label: "Cloudflareで公開", slug: "hub/cloudflare" },
            { label: "更新とバックアップ", slug: "hub/update-backup" },
          ],
        },
        {
          label: "デバイスを作る",
          items: [
            { label: "デバイス一覧", slug: "devices" },
            { label: "WTR 潅水デバイス", slug: "devices/wtr" },
            { label: "WRS 潅水・RS485", slug: "devices/wrs" },
            { label: "SOI / ENV センサー", slug: "devices/sensors" },
          ],
        },
        {
          label: "設定する",
          items: [
            { label: "圃場とデバイス", slug: "configure/fields-devices" },
            { label: "潅水", slug: "configure/watering" },
            { label: "設定項目リファレンス", slug: "configure/settings-reference" },
          ],
        },
        {
          label: "運用する",
          items: [
            { label: "日々の確認", slug: "operate/daily" },
            { label: "F/W・OTA更新", slug: "operate/firmware" },
          ],
        },
        {
          label: "トラブルシューティング",
          items: [
            { label: "問題から探す", slug: "troubleshoot" },
            { label: "デバイスがオフライン", slug: "troubleshoot/device-offline" },
            { label: "潅水されない", slug: "troubleshoot/watering" },
            { label: "設定が反映されない", slug: "troubleshoot/config" },
          ],
        },
        {
          label: "リファレンス",
          items: [
            { label: "ピンアサイン", slug: "reference/pins" },
            { label: "Runtime Config", slug: "reference/runtime-config" },
            { label: "互換性と制約", slug: "reference/compatibility" },
          ],
        },
        {
          label: "サポート",
          items: [{ label: "Discord Community", slug: "community" }],
        },
      ],
      head: [
        { tag: "meta", attrs: { name: "theme-color", content: "#153f33" } },
        { tag: "meta", attrs: { property: "og:locale", content: "ja_JP" } },
      ],
    }),
  ],
});
