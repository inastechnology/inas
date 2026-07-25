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
      customCss: ["./src/styles/custom.css", "./src/styles/manual.css", "./src/styles/visual-guides.css"],
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
            { label: "INASを使う人へ", slug: "start/why-inas" },
            { label: "INASのしくみ", slug: "start/overview" },
            { label: "利用方法を選ぶ", slug: "start/choose-path" },
            { label: "使うWi-Fiを準備", slug: "start/network" },
            { label: "提供機器（準備中）", slug: "start/provided-hardware" },
            { label: "安全上の注意", slug: "start/safety" },
          ],
        },
        {
          label: "運用する",
          items: [
            { label: "日々の確認", slug: "operate/daily" },
            { label: "AI栽培計画と作業提案", slug: "operate/ai-calendar" },
          ],
        },
        {
          label: "設定する",
          items: [
            { label: "画面の設定ガイド", slug: "configure/settings" },
            { label: "圃場とデバイス", slug: "configure/fields-devices" },
            { label: "潅水を設定", slug: "configure/watering" },
          ],
        },
        {
          label: "困ったとき",
          items: [
            { label: "問題から探す", slug: "troubleshoot" },
            { label: "デバイスがオフライン", slug: "troubleshoot/device-offline" },
            { label: "潅水されない", slug: "troubleshoot/watering" },
            { label: "設定が反映されない", slug: "troubleshoot/config" },
          ],
        },
        {
          label: "サポート",
          items: [{ label: "Discord Community", slug: "community" }],
        },
        {
          label: "開発者ドキュメント",
          collapsed: true,
          items: [
            { label: "開発者向け入口", slug: "technical" },
            { label: "技術構成と責務", slug: "technical/architecture" },
            { label: "通信・ネットワーク詳細", slug: "technical/networking" },
            { label: "アプリ設定の技術ガイド", slug: "technical/app-settings" },
            { label: "電気・潅水設備の安全要件", slug: "technical/hardware-safety" },
            { label: "機器を選んで購入", slug: "start/hardware" },
            { label: "購入前チェック", slug: "start/prerequisites" },
            { label: "自己構築の全手順", slug: "start/quickstart" },
            { label: "Raspberry Piを準備", slug: "hub/raspberry-pi" },
            { label: "Hubをインストール", slug: "hub/install" },
            { label: "Cloudflareで公開", slug: "hub/cloudflare" },
            { label: "更新とバックアップ", slug: "hub/update-backup" },
            { label: "機器ソフトウェア更新", slug: "operate/firmware" },
            { label: "デバイス一覧", slug: "devices" },
            { label: "WTR 潅水デバイス", slug: "devices/wtr" },
            { label: "WRS 潅水・RS485", slug: "devices/wrs" },
            { label: "SOI / ENV センサー", slug: "devices/sensors" },
            { label: "機器設定キー", slug: "configure/settings-reference" },
            { label: "ピンアサイン", slug: "reference/pins" },
            { label: "機器設定の配信仕様", slug: "reference/runtime-config" },
            { label: "互換性と制約", slug: "reference/compatibility" },
          ],
        },
      ],
      head: [
        { tag: "meta", attrs: { name: "theme-color", content: "#153f33" } },
        { tag: "meta", attrs: { property: "og:locale", content: "ja_JP" } },
        { tag: "script", attrs: { src: "/manual-lightbox.js", defer: true } },
      ],
    }),
  ],
});
