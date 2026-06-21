# AlgoTrade — Ürünleşme Yol Haritası (Tasarım Dokümanı)

- **Tarih:** 2026-06-21
- **Durum:** Onaylandı (kullanıcı incelemesi bekliyor)
- **Repo:** github.com/kbur4k-kbur4k/AlgoTrade (private)

---

## 1. Problem ve Bağlam

Mevcut kod tabanı (`wallet_manager`, ~55K satır, 110+ modül) mühendislik açısından
iddialı: 4 modelli ML ensemble, "Risk/Execution/Promotion/Learning OS" katmanları,
Docker/k8s, Prometheus/Grafana, 3155 test. Ancak inceleme şunu ortaya koydu:

- **Kanıtlanmış edge yok.** Yerel `paper_trades`=0 satır, `quant_analytics.db` boş.
  Tüm canlı veri kapanan Azure sunucusundaydı.
- **Overfit metrikleri sahte.** `training_report.json` içinde tüm modellerde
  `deflated_sharpe=1.0`, `feature_stability=0.0` — hesaplanmıyor (placeholder).
- **"4 model" pratikte 2.** XGBoost/LSTM reddedilmiş; aktif sadece LightGBM (%55)
  + Transformer (%43 win-rate, kabul mantığı şüpheli).
- **Maliyet körlüğü.** `execution_logic.py:768` → `gas_cost_usd=0.0` sabit. Sistem
  gas/komisyonu kâr-zarara katmıyor → bot durmadan minik (~$0.05) trade atıp
  churn yapıyor.
- **Çalıştırma engeli.** Bot çalışmak için `.env` (VAULT_KEY, Telegram, RPC) +
  `wallets.json` istiyor; bulut-servis varsayımıyla yazılmış, lokal akış yok.
- **Aşırı mühendislik + ölü kod.** Gölgelenmiş `alerting.py`, 4 ölü
  `task_factories_*` stub, 11 "OS" katmanı, 37 strateji modülü, mükerrer dosyalar.

**Sonuç:** İşin kolay-gösterişli kısmı (altyapı) aşırı yapılmış; tek önemli kısım
(maliyet-sonrası kanıtlanmış edge) eksik.

## 2. Hedef ve Kısıtlar

**Hedef:** Kanıtlanmış, doğrulanabilir bir track record'a sahip; temiz, profesyonel
bir **paper-trading** kuant sistemi. Ürün/gerçek-para kararı edge kanıtlandıktan
SONRA verilir.

**Kısıtlar (kullanıcı tarafından netleştirildi):**
- **Şu an gerçek para YOK** — sadece paper trading.
- İş modeli (SaaS / sinyal / altyapı) **şimdilik açık** — edge kanıtına kadar
  ertelendi; tüm yolları açık tutacak şekilde inşa edilecek.
- **Yeni MCP / 3. parti plugin eklenmeyecek** — mevcut set yeterli; tek katma-değer
  projeye özel `run-backtest` skill'i (Faz 1'de).
- Bütçe: minimum bulut ($0-20/ay); önce kanıt, sonra yatırım.

## 3. Seçilen Yaklaşım: "Doğrulama-önce, lokal-önce" (A)

Değerlendirilen alternatifler:
- **(A) Doğrulama-önce** — yeni özelliği durdur, edge'i kanıtla, sadeleştir, sonra
  ürünleştir. **← Seçildi.**
- (B) Hemen platformu ürünleştir — kanıtlanmamış edge üstüne vitrin; itibar/hukuk
  riski. **Reddedildi.**
- (C) Altyapıyı ürünleştir (alpha'yı değil) — "DeFi kuant backtest framework".
  A başarısız/marjinal çıkarsa **nihai ürün yolu** olarak saklanır.

**Karar:** A ile başla, çekirdeği C'ye uygun (yeniden kullanılabilir kuant motoru)
biçimde inşa et — edge çıkarsa ürün hazır olur.

## 4. Birinci-sınıf Tasarım Bileşeni: Trade Quality Gate

Kullanıcının "günde birkaç düzgün trade, çöp trade yok" isteği + churn teşhisi tek
mekanizmayla çözülür. Bir trade **ancak şu üçü birden** sağlanırsa açılır:

1. **Conviction:** sinyal olasılığı 0.5'ten yeterince uzak (yükseltilmiş, ayarlanabilir eşik).
2. **Net beklenen kazanç > maliyet + marj:**
   `beklenen_hareket_bps − (gas + DEX_fee + slippage)_bps − güvenlik_marjı > min_kâr_hedefi_bps`.
3. **Minimum bekleme/cooldown:** son trade'den beri minimum süre → günde işlem sayısına doğal sınır.

Tunable hedef: "günde ~N trade, her biri ≥ X bps net beklenti". Aynı net-maliyet
hesabı Faz 1 backtest'inin de çekirdeği — bir taşla iki kuş.

## 5. Fazlar

### Faz 0 — Temizlik & Lokal Çalıştırma (1-2 gün, risksiz)
- Ölü kod sil: gölgelenmiş `alerting.py`, 4 `task_factories_*` stub, kök artıkları,
  `.bak`'lar, `wallet_manager/ml_models/archive/`.
- `requirements.txt`'i kurulu sürümlere pinle + lock; tekrar-üretilebilirlik.
- Bağlanmamış modülleri (prometheus_webhook, alpha_decay_monitor, ensemble_weighter,
  market_microstructure, log_schema, rate_limiter) gözden geçir: bağla ya da sil.
- **Lokal smoke script:** secret'sız, paper-modda botu kullanıcının makinesinde
  ayağa kaldıran tek komut. *(Çıktı: "çalışıyor" kanıtı.)*

### Faz 1 — Dürüst Doğrulama Motoru (EN KRİTİK)
- `gas_cost_usd=0.0` bug'ını düzelt → gerçekçi maliyet modeli (Base gas + DEX fee + slippage).
- **Trade Quality Gate**'i birinci-sınıf, ayarlanabilir bileşen olarak kur.
- `deflated_sharpe` ve `feature_stability`'yi gerçekten hesapla.
- `backtester.py`'yi runtime'a bağla; 3 yıllık veride walk-forward, out-of-sample koş.
- Projeye özel **`run-backtest` skill'i** (skill-creator ile).
- **KARAR KAPISI:** net Sharpe ve getiri anlamlı pozitif mi?
  - Hayır → strateji/feature'a dön ya da (C)'ye pivot.
  - Evet → Faz 2.

### Faz 2 — Çekirdeği Sadeleştir (edge kanıtlanırsa)
- 11 "OS" + 37 stratejiyi gerçekten katkı verenlere indir (her birinin IC'sini ölç).
- Mükerrerleri birleştir: `continuous_learning`↔`learning_os`, iki `signal_intelligence`,
  orchestrator ailesi.
- Net modül sınırları + arayüzler → yeniden kullanılabilir kuant motoru.

### Faz 3 — Ucuz, Profesyonel Paper Çalıştırma
- En ucuz bulut (veya lokal) + Docker; mevcut Prometheus/Grafana.
- Faz 12'nin yarım kalan IC ölçümünü bitir; aylar boyu kesintisiz, doğrulanabilir
  paper track record biriktir.

### Faz 4 — Ürün Kararı (decision gate)
- Kanıtlanmış track record + temiz çekirdek varken: SaaS / sinyal / altyapı (C)
  kararını veriyle ver. Gerçek para hâlâ opsiyonel.
- CV vitrini: kod private kalırken ayrı public showcase repo (README + mimari +
  sonuç grafikleri, kod yok).

## 6. Model Seçimi (çalışma verimi)
- Faz 0 (mekanik): Sonnet / Opus fast.
- Faz 1 (kritik muhakeme): **Opus 4.8 + high reasoning** — cimrilik etme.
- Faz 2: karar için Opus high, uygulama için Sonnet.
- Faz 3-4: Sonnet.

## 7. Kapsam Dışı (YAGNI)
- Gerçek para / canlı trading (`LIVE_TRADING_ENABLED` false kalır).
- Yeni MCP / 3. parti plugin.
- Yeni "OS" katmanı / strateji eklemek.
- Ürün/UI geliştirme (Faz 4 karar kapısına kadar).

## 8. Başarı Kriteri
- **Faz 0:** Bot lokalde paper-modda tek komutla çalışıyor; repo temiz.
- **Faz 1:** Tek dürüst rapor — maliyet-sonrası net Sharpe, getiri, max drawdown,
  trade/gün. Edge kararı net.
- **Genel:** Edge kanıtlanır VEYA çürütülür; her iki sonuçta da net bir sonraki adım.
