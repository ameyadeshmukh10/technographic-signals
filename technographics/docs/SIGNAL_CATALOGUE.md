# Technographic Signal Catalogue

> The complete inventory of technologies this agent can detect on a company's
> web presence, the taxonomy that organizes them, why the detection is accurate,
> and how the system is configured for a specific client.

## Executive summary

| Metric | Count |
|---|---:|
| **Total vendors in the library** | **7,528** |
| Detectable via the **JS / Web pipeline** | 7,444 |
| Detectable via the **DNS pipeline** | 88 |
| Hand-curated, high-precision signatures | 36 |
| Wappalyzer categories | 108 |
| Top-level domains (this document's taxonomy) | 12 |

Two independent detection pipelines share one vendor taxonomy:

1. **DNS pipeline** — inspects CNAME / TXT / MX / NS / SOA / A records. Catches
   infrastructure and back-office tools that leave no front-end trace — e.g.
   Marketo via a `*.mktoweb.com` CNAME, SendGrid via an SPF `include:sendgrid.net`,
   Microsoft 365 via `*.mail.protection.outlook.com`.
2. **JS / Web pipeline** — inspects script `src` URLs, JS `window.*` globals,
   cookies, response headers, HTML, and meta tags from the rendered page.

A vendor can be detected by **both** pipelines; results are fused. The two tiers
of signatures — a hand-curated core and the imported Wappalyzer master library —
are merged at load time, with **curated signatures overriding** the master entry
for the same vendor (so hand-tuned precision always wins).

_Generated from the live library (upstream commit `c2855b4652`). Regenerate with
`PYTHONPATH=src python scripts/gen_signal_catalogue.py`._

## How detection works (high level)

For each target domain the agent runs two collectors and two matchers, then fuses
the results:

```
                 ┌─────────────── domain ───────────────┐
                 ▼                                       ▼
        DNS collector (dnspython)            Web collector (Playwright / requests)
        A · MX · TXT · NS · SOA · CNAME      script srcs · window globals · cookies
                 │                            headers · HTML · meta tags
                 ▼                                       ▼
           DNS matcher                              Web matcher
                 │                                       │
            [Detection]  ──────── fusion (noisy-OR) ──────  [Detection]
                                       │
                                  ranked detections
```

**Signature schema.** Every signal is a `Pattern` = `{value, match_type, strength}`:

- **5 match types** — `exact`, `contains`, `prefix`, `suffix`, `regex`
  (case-insensitive; DNS values are dot-normalized).
- **4 strength buckets** — `definitive (1.0)`, `strong (0.85)`, `moderate (0.6)`,
  `weak (0.3)`.

A vendor groups many patterns across channels (script srcs, JS globals, cookie
prefixes, headers, HTML, meta, and the DNS record types).

**Confidence per vendor.** `base = max(strength of matched patterns)`, plus a
small corroboration boost `0.05 × (matches − 1)` capped at `+0.15`, clamped to
`1.0`. More independent signals → higher confidence, but a single definitive
signal already scores high.

**Fusion.** When DNS and Web both flag a vendor, confidences combine with a
**noisy-OR**: `1 − (1 − dns) × (1 − web)` — agreement across independent
pipelines pushes confidence up.

**Rendering enrichment.** The web collector can execute the page (headless
Chromium) and enumerate `window.*`, capturing tools that inject themselves at
runtime (Microsoft Clarity, Hotjar, Demandbase, Meta Pixel…) and are invisible to
a static HTML fetch.

Implementation lives in `schema.py`, `dns_matcher.py`, `web_matcher.py`,
`fusion.py`, the collectors, and the integration adapter `src/detectors/engine.py`.

## Why it is high-accuracy

- **Independent, corroborating channels.** A vendor is rarely judged on one clue:
  script src + JS global + cookie + DNS record all vote. The confidence formula
  rewards agreement, and fusion rewards agreement *across pipelines* (a web hit
  plus a DNS hit is near-certain).
- **DNS signals are hard to fake.** CNAME/MX/TXT/SOA records reflect real
  infrastructure choices (email vendor, CDN, marketing-domain setup). They can't
  be spoofed by a tag a competitor copied, and they reveal tools with no
  front-end footprint at all.
- **Precise patterns, not keyword soup.** Patterns are anchored regexes on script
  hosts, cookie *name prefixes*, exact `window` globals, and specific DNS targets
  — chosen to fire on the vendor and nothing else. Strength weighting demotes
  shared/ambiguous signals (e.g. a generic `gtag.js` loader is weak; the
  `AW-` conversion id is strong).
- **Rendered window-globals.** Executing the page catches runtime-injected tools
  that static scanners miss, materially raising recall on modern JS sites.
- **Tier indicators.** Selected vendors carry `paid` / `enterprise` indicators
  (e.g. a custom Intercom Help Center domain implies a paid plan), adding
  qualitative signal beyond "present / absent".
- **Curated overrides + provenance.** A hand-tuned core overrides the bulk import
  per-vendor; every imported pattern records its source in `notes`, so signals
  are auditable and improvable.
- **Guardrails.** A schema linter (`technographics validate`) checks every
  signature file, and the package ships a test suite (96 tests) covering the
  matchers, loader, fusion, and importer.

## The signal taxonomy

All 108 categories (plus two curated additions — *Sales engagement*, *Data infrastructure*) roll up into 12 domains. ★ marks a hand-curated signature. Full per-vendor lists are in [Appendix A](#appendix-a--full-vendor-enumeration).

### Sales & CRM  ·  443 vendors
_Pipeline, accounts, and revenue tooling._  (web: 442 · DNS: 3)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| CRM | 255 | 2 | Salesforce★, Agile CRM, Aidbase, Airship CRM, Aiva, Alumni Channel, Amilia, amoCRM, Anexis, Anthology Encompass, Apodle, Arketa |
| Customer data platform | 54 | 1 | mParticle★, Rudderstack★, Segment★, Able CDP, Acquia Customer Data Platform, Adobe Experience Platform Identity Service, Antsomi CDP 365, Aptania, Asapp, Bandwango, BlueConic, Bread & Butter |
| Appointment scheduling | 129 |  | Calendly, Chili Piper, A2Z Events, Acceptd, Acuity Scheduling, AddEvent, Agendize, Aimy, Allbookable, Appointedd, Appointo, Appointy |
| Sales engagement | 5 |  | AiSDR★, Factors.ai★, G2★, Reo.dev★, Outreach★ |

### Marketing Automation & Messaging  ·  728 vendors
_Lifecycle, email, and campaign engines._  (web: 718 · DNS: 18)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| Marketing automation | 499 | 8 | Customer.io★, HubSpot★, Klaviyo★, Marketo★, Salesforce Marketing Cloud Account Engagement (Pardot)★, Salesloft★, 6sense, ActiveCampaign, Braze, Constant Contact, Iterable, MailChimp |
| Email | 34 | 6 | Amazon SES, Mailgun, Sendgrid, Aument, Benchmark, BIGLIST, Clearout, CleverReach, Doppler, Emaileri, EmailJS, Envoke |
| Webmail | 13 | 4 | Google Workspace★, Microsoft 365★, Apple iCloud Mail, CrossBox, Open-Xchange App Suite, Outlook Web App, Proton Mail, RainLoop, RoundCube, SquirrelMail, Sympa, Zadarma |
| Cart abandonment | 16 |  | CareCart, CareCart Cartly Abandoned Cart Recovery, CartBot, CartHook, CartRocket, CartStack, GetRooster, Keptify, OptiMonk, PushOwl Web Push Notifications, Recapture, Recart |
| Loyalty & rewards | 40 |  | 99minds, Antavo, Appstle, Beans, BON Loyalty, Captain Up, CleverInsight, Eber, Fondue, Gameball, Glow, HeyPongo |
| Referral marketing | 23 |  | Aklamio, Ambassador, Buyapowa, CloudSponge, ContextBar, Coopt, EarlyParrot, Extole, Flocktory, Friendbuy, Guuru, Indi |
| Affiliate programs | 62 |  | A8.net, AccessTrade, Admitad, Affilae, Affiliate B, Affiliate Future, Affiliatly, Affilio, Affilo, Amazon Associates, AWIN, Backstage |
| Fundraising & donations | 41 |  | ActBlue, AlumnIQ, Arreva, BackerKit, Blackbaud CRM, BRYNK, Classy, Click & Pledge, Community Funded, CustomDonations, Donorbox, DonorPerfect |

### Advertising & Tag Management  ·  240 vendors
_Paid media pixels, retargeting, and tag containers._  (web: 239 · DNS: 0)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| Advertising | 211 |  | Google Ads★, Criteo, Linkedin Ads, Microsoft Advertising, Reddit Ads, Snap Pixel, Taboola, Twitter Ads, 33Across, Aarki, AcuityAds, AD EBiS |
| Retargeting | 18 |  | Blue, Captify, Cross Pixel, Fixel, Linx Impulse, Meazy, Notix, PebblePost, Picreel, Revenue Roll, RTB House, SharpSpring Ads |
| Tag managers | 11 |  | Google Tag Manager, Tealium, Adobe DTM, Adobe Experience Platform Launch, Commanders Act TagCommander, Ensighten, Facebook Pixel Advanced Matching, Matomo Tag Manager, TagPro, Yahoo! Tag Manager, Yottaa |

### Analytics & Optimization  ·  780 vendors
_Measurement, experimentation, and personalization._  (web: 780 · DNS: 1)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| Analytics | 397 | 1 | Amplitude★, FullStory★, Google Analytics★, Heap★, Mixpanel★, Albacross, Clearbit Reveal, Contentsquare, Demandbase, Facebook Pixel, Gong, Google Ads Conversion Tracking |
| RUM | 18 |  | Akamai mPulse, Amazon CloudWatch RUM, Atatus, Datadog, Dynatrace RUM, Eggplant, Microsoft Application Insights, New Relic, Pingdom RUM, Quanta, Raygun, Rumvision |
| A/B Testing | 40 |  | AB Tasty, Optimizely, ABLyft, Adobe Target, Bringie, Bunting, Complianz, Convert, Dexter, Dynamic Yield, Estore Compare, Google Optimize |
| Personalisation | 143 |  | 4-Tell, Adaptix, Adnymics, Adoric, Apptus, Attentive, Barilliance, Beyable, bluebarry, Blueknow, Bold Commerce, Bounce Commerce |
| Segmentation | 8 |  | Adobe Audience Manager, Bloom Labs, Omeda, Oracle BlueKai, Poltio, Salesforce Audience Studio, Tealium AudienceStream, Viafoura |
| Surveys | 43 |  | Typeform, Bestie, Brandquiz, Clicktools, coUrbanize, Crowdsignal, CustomerSure, Delighted, Doorbell, EasyPolls, Emojicom, Enalyzer |
| User onboarding | 18 |  | Appcues, Arengu, Canopy Connect, Chameleon, Checkin, Elevio, FintechOS, Hansel, LOU, PeerPal, Poper, Stonly |
| SEO | 35 |  | Ahrefs, All in One SEO, All in One SEO Pack, Alli, Atomseo, Attracta, Auto HQ, BlogHunch, BrightEdge, BrightLocal, ePublishing, Farazi Bilişim |
| Content curation | 36 |  | Bazaarvoice Curation, Ceros, Cevoid, ContentBot, ContentGems, Contently, Contents, ContentStudio, Covet.pics, CPEx, Curated, Emplifi UGC |
| Form builders | 42 |  | Airform, Basin, Campflow, Digioh, Form.io, Form.taxi, Formaloo, FormAssembly, FormBold, FormBucket, Formcake, Formcan |

### Customer Support & Engagement  ·  523 vendors
_Chat, helpdesk, reviews, and on-site engagement._  (web: 523 · DNS: 1)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| Live chat | 361 | 1 | Intercom★, Pipedrive★, Front Chat★, Gorgias★, Drift, Qualified, 11Sight, 42Chat, 8x8, Acquire Live Chat, ActivEngage, Ada |
| Reviews | 100 |  | Alchemer Mobile, Ali Reviews, Alpha Review, Appzi, AskNicely, Avis Verifies, Bazaarvoice Reviews, Clutch, Contlo, Customer Alliance, Famewall, FeatherX |
| Comment systems | 14 |  | Annoto, Cackle, Commento, Cove, Disqus, Giscus, IntenseDebate, Isso, Livefyre, Question2Answer, ReplyBox, Twikoo |
| Translation | 12 |  | Bablic, ConveyThis, Conword, Crowdin, Easyling, langify, Linguise, Pluglin, Smartling, Transcy, Weblate, Weglot |
| Accessibility | 36 |  | AccessiBe, Accessibility Toolbar Plugin, Accessible360, Accessibly, AccessiWay, Adally, AdaSiteCompliance, All in One Accessibility, Allyable, Allyant, AudioEye, digi·access |

### Commerce  ·  1,376 vendors
_Storefronts, payments, fulfilment, and post-purchase._  (web: 1,375 · DNS: 3)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| Ecommerce | 761 | 2 | BigCommerce, Magento, Shopify, WooCommerce, 24nettbutikk, 2ClickShop, 42stores, 4Partners CMS, 91App, Aacio, Aasaan, AbanteCart |
| Ecommerce frontends | 16 |  | Aiden, Argento, Breeze, Deco.cx, E-Com Plus, Front-Commerce, GoMage, Hyva Themes, Kickflip, Makaira, Platter, PWA Studio |
| Shopify apps | 142 |  | Accentuate Custom Fields, AdNabu, Alia, Autocommerce, Autoketing Product Reviews, Avada AVASHIP, Avada Boost Sales, Avada SEO, Avada Size Chart, Back In Stock, Beam AfterSell, Beam OutSell |
| Shopify themes | 3 |  | Belliza, Conversion Bear, Shoptimized |
| Payment processors | 166 | 1 | Adyen, Afterpay, Braintree, PayPal, Stripe, Affirm, Amazon Pay, American Express, Amex Express Checkout, Aplazame, Apple Pay, Apxium |
| Buy now pay later | 33 |  | Addi, Atome, cashew, Deko, etika, Fundiin, HeyLight, hoolah, Humm, LatitudePay, LayBuy, Limepay |
| Returns | 15 |  | AfterShip Returns Center, EyeFitU, Happy Returns, Loop Returns, Narvar, ParcelPanel, Refundid, Reshop, Returnflows, ReturnGO, Returnly, Seel |
| Shipping carriers | 68 |  | 4Partners, APC, Asendia, Australia Post, B2C Europe, Billbee, Bleckmann, Boxtal, Bpost, BRT, Budbee, Celeritas |
| Fulfilment | 12 |  | AfterShip, Bobgo, Deliverr, Descartes, Enviopack, Extend, Malomo, MapMyChannel, Planzer, Route, Shoprunner, VeraCore |
| Reservations & delivery | 96 |  | Aspio, BedBooking, Bobonus, BokaBord, Bookatable, BookDinners, Booking Experts, Booking Factory, Bookteq, Bottle, Clock PMS, Clorder |
| Ticket booking | 53 |  | Adalte, Agoda, Airdata, Asksuite, Beyonk, Bileto, Book N Pay, Busify, ClickBus, Cooltix, Dice, Droplabs |
| Cross border ecommerce | 11 |  | Borderfree, ESW, Exemptify, Flow, Global-e, GlobalShopex, Glopal, Localised, With Reach, WorldShopping, Zonos |

### Content & Web Platforms  ·  1,387 vendors
_CMS, site builders, and content systems._  (web: 1,383 · DNS: 2)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| CMS | 493 |  | Contentful, Drupal, Squarespace, Wix, WordPress, 1C-Bitrix, 321 CMS, 6Valley eCommerce CMS, a-blog cms, AbhiCMS, AboutMyClinic, AdminBuy |
| Page builders | 210 |  | Webflow, Acquia Site Studio, Adalo, Adobe Portfolio, Alboom Prosite, AllMyLinks, ApexPages, Appjustable, Appy Pie Builder, Art Schema, Assemble, B12 |
| WordPress plugins | 192 |  | a3 Lazy Load, AddToAny Share Buttons, Advanced Custom Fields, Age Gate, Akismet, AMP for WordPress, Animate It, Animation Addons, Asgaros Forum, Astra Widgets, Autoptimize, Beaver Builder |
| WordPress themes | 152 |  | AFThemes CoverNews, AitThemes, AndersNoren Baskerville, AndersNoren Fukasawa, AndersNoren Hemingway, AndersNoren Hitchcock, AndersNoren Lovecraft, Apollo13Themes Rife, Astra, aThemes Airi, aThemes Astrid, aThemes Hiero |
| Blogs | 23 |  | Aegea, Bear Blog, Beehiiv, Blogger, BUROGU, Dotclear, DropInBlog, Haloscan, Hashnode, Jugem, LiveJournal, Medium |
| Wikis | 12 |  | Apache JSPWiki, Atlassian Confluence, DokuWiki, Foswiki, ikiwiki, MediaWiki, MoinMoin, PukiWiki, TWiki, WikkaWiki, XWiki, YesWiki |
| Documentation | 48 | 1 | Zendesk★, Intercom Articles, Adobe RoboHelp, Apigee, Asciidoctor, BetterDocs, BookStack, Bump, ClickHelp, ClickUp, DocFX, Docsify |
| Photo galleries | 24 |  | Alboom Proof, Blessing Skin, Bloom Portfolio, bxSlider, Canvy, Chevereto, Clickbooq, Coppermine, Gallery, Imagekit, JAlbum, Keepeek |
| Static site generator | 29 |  | Adobe Muse, Astro, Bridgetown, Cecil, Eleventy, Gatsby, Gridsome, GuppY, Hexo, Hugo, Jekyll, Lume |
| Message boards | 47 |  | bbPress, Circle, CometD, Community, Copiny, Countable, Discourse, Discuz! X, ElkArte, Flarum, FluxBB, Forumbee |
| LMS | 72 |  | Absorb, AccessAlly, Accredible, Aforest LMS, aSc EduPage, Canvas LMS, Chamilo, Classeh, Clever, Coachy, Dokeos, EAD Plataforma |
| DMS | 13 |  | Clicksign, Clinked, Data8, DSpace, Evernote, Invenio, Koha, Onehub, Open Journal Systems, Paperless Pipeline, ProductDyno, Typeflo |
| Digital asset management | 32 | 1 | Adobe Dynamic Media Classic, Aprimo, Aryeo, Blippa, Bluestone PIM, Brandfolder, Bynder, Canto, Celum, Censhare, CollectiveAccess, Corebook |
| Editors | 22 |  | Adobe GoLive, Amaya, BannerBoo, Blockly, Bluefish, CodeMirror, Draft.js, DreamWeaver, EditPlus, FrontPage, iWeb, Microsoft Excel |
| Rich text editors | 14 |  | Ace, CKEditor, Edit-in-Place, Editor.js, Etherpad, FreeTextBox, Froala Editor, Monaco Editor, N1ED, PSPad, Quill, TinyMCE |
| Feed readers | 4 |  | AnnounceKit, Beehiiv RSS feed, Blendle, Planet |

### Web Development & Frameworks  ·  991 vendors
_Front-end libraries, frameworks, and media._  (web: 982 · DNS: 1)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| JavaScript libraries | 235 |  | Apollo★, jQuery, @sulu/web, _hyperscript, Amaze UI, Amplify JS, AnythingSlider, AOS, ARM JS, autoComplete.js, Axios, Barba.js |
| JavaScript frameworks | 85 |  | Angular, Next.js, React, Vue.js, Adobe Client Data Layer, Ajax.NET Professional, AlertifyJS, AlloyUI, Alpine.js, AMP, AngularJS, Aurelia |
| JavaScript graphics | 63 |  | A-Frame, amCharts, Angular Gridster, anime.js, AntV G2, AntV G6, ApexCharts.js, Arbor.js, Babylon.js, Backstretch, Bokeh, CanvasJS |
| Web frameworks | 92 |  | ABP Framework, actionhero.js, Adobe ColdFusion, AdonisJS, Akka HTTP, Amber, AngularDart, Apache Wicket, Arwes, Aseqbase, ASP.NET Boilerplate, Blade |
| UI frameworks | 91 |  | Bootstrap, Tailwind CSS, Angular Material, Animate.css, Ant Design, Arco Design Vue, augmented-ui, Aura, Automatic.css, Base UI, Basil.css, Bulma |
| Mobile frameworks | 7 |  | Framework7, jQTouch, jQuery Mobile, jQuery-pjax, Onsen UI, starti.app, Wink |
| Programming languages | 29 |  | Adobe Flash, bun, C, CFML, Dart, Dragon, Elixir, Elm, Erlang, GeneXus, Go, GraphQL |
| Font scripts | 19 |  | Adobe Fonts, Bootstrap Icons, Bunny Fonts, Cufon, Emfont, Font Awesome, FontServer, Fork Awesome, Glyphicons, Google Font API, Hoefler&Co, i30con |
| Widgets | 206 |  | Outbrain, AccuWeather, AddShoppers, AddThis, AddToAny, AirRobe, Airtable, Algolia DocSearch, Answerbase, AnswerDash, AppuOnline, Arena |
| Maps | 36 |  | Amap, Apple MapKit JS, ArcGIS API for JavaScript, Baidu Maps, CARTO Analytics, ClustrMaps Widget, Develic Omnium Maps, EagleView, Geoapify, Google Maps, Here, Leaflet |
| Video players | 47 |  | 30namaPlayer, Aniview Video Ad Player, Artplayer.js, Asciinema, Bitmovin, Blinklink, Brightcove, Cleeng, Clipara, Cloudflare Stream, Conviva, Dailymotion |
| Livestreaming | 19 | 1 | Apizee, Bambuser, BigMarker, Confer With, Dyte, EasyWebinar, Firework, Go Instore, Hero, HeySummit, Klarna Virtual Shopping, Loom |
| Media servers | 7 |  | Ausha, AzuraCast, BigPoint, Muvi, Odeum, Sardius Media, Uplynk |
| Augmented reality | 26 |  | <model-viewer>, Auglio, Cylindo, DeepAR, DressOn, Expivi, Fittingbox, Floori, Levar, Luna, mirrAR, Modelo |
| Geolocation | 19 |  | BigDataCloud IP Geolocation, Bullseye, db-ip, Geo Targetly, Geobytes, ip-api, IP2Location.io, ipapi, ipapi.co, ipbase, ipdata, ipgeolocation |
| Feature management | 10 |  | Beamer, Blesta, Featurebase, FlagSmith, LaunchDarkly, LaunchNotes, Noticeable, Olvy, Split, Upvoty |

### Infrastructure, Hosting & CDN  ·  431 vendors
_Where and how the site is served._  (web: 381 · DNS: 52)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| CDN | 65 | 6 | Akamai★, Cloudflare★, Fastly★, Amazon CloudFront, 5centsCDN, Acquia Cloud Platform CDN, Airee, Alibaba Cloud CDN, Amazon S3, Arc, ArvanCloud, Azion |
| Hosting | 53 | 35 | 34SP.com, Acquia Cloud Site Factory, ALL-INKL, ANS, Aruba.it, Bluehost, Contabo, DomainFactory, Doteasy, DreamHost, Drupal Multisite, Elementor Cloud |
| Hosting panels | 13 |  | AlternC, BILLmanager, cPanel, Creoline, DirectAdmin, FeatherPanel, i-MSCP, Novaresa, Plesk, Pterodactyl Panel, TCAdmin, Tencent Waterproof Wall |
| PaaS | 51 | 8 | Amazon Web Services, Netlify, Vercel, Acquia Cloud Platform, Agora, Akamai Connected Cloud, Appian, Azure, Bask Health, Bernet Cloud, Brimble, Chabokan |
| IaaS | 7 | 1 | Google Cloud, Alibaba Cloud Object Storage Service, Amazon ECS, Clientacquisition, Dweet, Leaseweb, Parmin Cloud |
| Web servers | 82 |  | Nginx, Amazon EC2, Angie, AOLserver, Apache APISIX, Apache HTTP Server, Apache Tomcat, Apache Traffic Server, Artifactory Web Server, CactiveCloud, Caddy, Centminmod |
| Web server extensions | 13 |  | Engintron, mod_auth_pam, mod_dav, mod_fastcgi, mod_jk, mod_perl, mod_python, mod_rack, mod_rails, mod_ssl, mod_wsgi, OpenSSL |
| Reverse proxies | 8 |  | Envoy, F5 BigIP, Hydra-Shield, IBM DataPower, Kong, MATORI.NET, Urllo, V2Board |
| Load balancers | 5 |  | Amazon ALB, Amazon ELB, Application Request Routing, Azure Front Door, Google Cloud Load Balancing |
| Caching | 16 |  | FastPixel, Google PageSpeed, LiteSpeed Cache, Litespeed Cache, NitroPack, Oracle Web Cache, RabbitLoader, RackCache, Redis Object Cache, Sitecore Experience Edge, Varnish, W3 Total Cache |
| Performance | 37 | 2 | AiSpeed, BerqWP, Blitz, Cloudflare Rocket Loader, Cloudflare Zaraz, Cronitor, Edgemesh, Fasterize, Google Cloud Trace, Gumlet, Hyperspeed, Intersection Observer |
| Containers | 4 |  | Docker, Harbor, Proxmox VE, PubNub |
| CI | 4 |  | Code Climate, GitLab CI/CD, Jenkins, TeamCity |
| Network storage | 4 |  | Amazon EFS, IPFS, Red Hat Gluster, Synology DiskStation |
| Network devices | 2 |  | Paessler, TeamViewer |
| Control systems | 3 |  | MapTrack, Milvus, Sedna System |
| Operating systems | 20 |  | AlmaLinux, Alpine Linux, CentOS, Darwin, Debian, Fedora, FreeBSD, Gentoo, Hirschmann HiOS, Raspbian, Red Hat, Scientific Linux |
| Databases | 17 |  | Amazon Aurora, Claris FileMaker, Cloudera, Dimensions AI, Firebase, Lucene, MariaDB, MongoDB, MySQL, Percona, PostgreSQL, PouchDB |
| Database managers | 7 |  | 8base, Adminer, Knack, phpMyAdmin, phpPgAdmin, SQL Buddy, Xano |
| Remote access | 12 |  | Atera, Cardina, CargoServer, Chaser, Citrix, Glance, Impero, Netop, Palo Alto Networks - GlobalProtect, Pulse Secure, ShellInABox, Upscope |
| Domain parking | 4 |  | Arsys Domain Parking, GoDaddy Domain Parking, JS.org, Verisign |
| Data infrastructure | 4 |  | Databricks★, Fivetran★, Hightouch★, Snowflake★ |

### Security, Privacy & Identity  ·  231 vendors
_Protection, consent, and authentication._  (web: 227 · DNS: 5)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| Security | 101 | 3 | Cloudflare Bot Management, reCAPTCHA, Accertify, adCAPTCHA, Akamai Bot Manager, Akamai Web Application Protector, Alibaba Cloud Verification Code, Altcha, AntiBot.Cloud, Anubis, Apruvd, ARCaptcha |
| Cookie compliance | 77 | 2 | Cookiebot, OneTrust, 2B Advice, Acconsento.click, AdFixus, AdOpt, AdRoll CMP System, Alfright, Axeptio, biskoui, Borlabs Cookie, Byscuit |
| Authentication | 38 |  | Auth0, Okta, Alliance Auth, Amazon Cognito, Apereo CAS, Apple Sign-in, Applied CSR24, Auth0 Lock, authorized.by, Authy, Azure AD B2C, Clerk |
| SSL/TLS certificate authorities | 7 |  | AWS Certificate Manager, DigiCert, Entrust, Identrust, Let's Encrypt, Sectigo, Thawte |
| Cryptominers | 8 |  | Coinhave, CoinHive, Coinimp, Crypto-Loot, deepMiner, JSEcoin, Minero.cc, Minerstat |

### Business Operations  ·  281 vendors
_Back-office and engineering operations._  (web: 281 · DNS: 1)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| Accounting | 9 |  | Akaunting, Carta, Epicor, Ignition, Iress, Lendi, Liscio, Taxdome, Tiller |
| Recruitment & staffing | 69 |  | 7Shifts, Agorize, Appcast, ApplicantStack, Avature, BambooHR, Beamery, BITE, Breezy HR, CATS, Converzee, Dover |
| Issue trackers | 68 | 1 | Atlassian Statuspage, Asana, Atlassian Jira, Atlassian Jira Issue Collector, Better Stack, BugHerd, Buglog, Bugzilla, Cachet, Canny, Checkly, Combodo iTop |
| Development | 75 |  | Acquia Cloud IDE, Anima, API Spreadsheets, Apiary, Appifiny, Appwrite, Artifactory, AskHandle, Atlassian Bitbucket, Atlassian FishEye, Betty Blocks, Canyon |
| Search engines | 60 |  | Addsearch, Algolia, Apisearch, Athena Search, Athos Commerce, Attraqt, Awesomplete, Baidu Search Box, Bloomreach Discovery, Boost Commerce, Cludo, Constructor.io |

### Miscellaneous  ·  117 vendors
_Everything else._  (web: 113 · DNS: 1)

| Category | Vendors | DNS | Notable |
|---|---:|---:|---|
| Miscellaneous | 117 | 1 | Acquia Content Hub, Acquire Cobrowse, Admiral, Azure Edge Network, Babel, Buildertrend, Buy with Prime, cgit, CoConstruct, Cocos2d, CopyPoison, DocuSign |

## The GTM lens (how the configured agent buckets signals)

The marketing/sales configuration collapses the master taxonomy into **four
output buckets** written to HubSpot's `technographic_signals` property. Because
the master library files ad pixels under *Analytics/Advertising* and intent tools
under *Analytics/Marketing automation*, a per-vendor override map
(`src/detectors/category_map.py`) re-routes them:

- **CRM** — Salesforce, HubSpot, Pipedrive
- **Ad Pixels** — Meta Pixel, Google Ads, Google Ads Conversion, Google Tag
  Manager, LinkedIn Insight Tag, LinkedIn Ads, TikTok, X/Twitter, Reddit,
  Pinterest, Microsoft Advertising (Bing UET), Snap, Quora
- **Martech** — Marketo, Pardot, Klaviyo, Mailchimp, Braze, Iterable, Customer.io,
  ActiveCampaign, Constant Contact, ConvertKit, Drip, SendGrid · Segment,
  RudderStack, mParticle, Tealium · Google Analytics, Mixpanel, Amplitude, Heap,
  Hotjar, FullStory, Contentsquare, Microsoft Clarity · Optimizely, VWO, AB Tasty ·
  Typeform
- **Salestech** — Outreach, Salesloft, Apollo · 6sense, Demandbase, ZoomInfo,
  Leadfeeder, Clearbit Reveal, Albacross, Warmly, Koala, Gong · Drift, Intercom,
  Qualified · Chili Piper, Calendly · G2, Factors.ai, Reo.dev, AiSDR

This 65-vendor set is the default `selection.marketing_sales.json`. A different
client gets a different selection (next section) — the four buckets and the
override map are reused.

## DNS signature catalogue

DNS detection resolves a domain's records and matches them against vendor patterns. Record types and what they typically reveal:

- **SOA / NS** — managed-DNS and hosting providers (the authoritative nameserver).
- **MX** — the email platform (Google Workspace, Microsoft 365, …).
- **TXT** — domain-verification and SPF includes (email senders, SaaS verifications).
- **CNAME** — vendor-hosted custom subdomains (marketing pages, help centers, trackers).

### Curated DNS signatures (13)
Hand-authored, GTM-focused, with paid/enterprise tier hints where applicable.

| Vendor | vendor_id | Records |
|---|---|---|
| Akamai | `akamai` | CNAME |
| Cloudflare | `cloudflare` | NS/CNAME |
| Customer.io | `customer_io` | CNAME |
| Fastly | `fastly` | CNAME |
| Google Workspace | `google_workspace` | TXT/MX |
| HubSpot | `hubspot` | CNAME |
| Intercom | `intercom` | TXT/CNAME |
| Klaviyo | `klaviyo` | CNAME |
| Marketo | `marketo` | CNAME |
| Microsoft 365 | `microsoft_365` | TXT/CNAME/MX |
| Salesforce | `salesforce` | CNAME |
| Salesforce Marketing Cloud Account Engagement (Pardot) | `pardot` | CNAME |
| Zendesk | `zendesk` | TXT/CNAME/MX |

### Master DNS signatures (81)
Imported from Wappalyzer — predominantly hosting/email/CDN providers.

| Vendor | vendor_id | Records |
|---|---|---|
| 34SP.com | `34sp_com` | SOA |
| ALL-INKL | `all_inkl` | SOA |
| Amazon CloudFront | `amazon_cloudfront` | CNAME |
| Amazon SES | `amazon_ses` | TXT |
| Amazon Web Services | `amazon_web_services` | NS |
| ANS | `ans` | SOA |
| Apple iCloud Mail | `apple_icloud_mail` | TXT/MX |
| Aruba.it | `aruba_it` | SOA |
| Atlassian Statuspage | `atlassian_statuspage` | TXT |
| Azion | `azion` | CNAME |
| Azure | `azure` | SOA/NS |
| Bluehost | `bluehost` | SOA/NS |
| Bugcrowd | `bugcrowd` | TXT |
| Cloudflare | `cloudflare` | SOA/NS |
| Contabo | `contabo` | SOA |
| Detectify | `detectify` | TXT |
| DocuSign | `docusign` | TXT |
| DomainFactory | `domainfactory` | SOA |
| DreamHost | `dreamhost` | SOA/NS |
| Dropbox | `dropbox` | TXT |
| FastComet | `fastcomet` | SOA |
| Funding Choices | `funding_choices` | SOA |
| GoDaddy | `godaddy` | SOA/NS |
| Google Workspace | `google_workspace` | MX |
| Gumroad | `gumroad` | CNAME |
| Helhost | `helhost` | SOA/NS |
| Heroku | `heroku` | TXT |
| Hetzner | `hetzner` | SOA/NS |
| Hostens | `hostens` | SOA |
| HostEurope | `hosteurope` | SOA |
| Hostgator | `hostgator` | SOA |
| Hosting Ukraine | `hosting_ukraine` | SOA |
| Hostinger | `hostinger` | SOA |
| Hostiq | `hostiq` | SOA |
| Hostpoint | `hostpoint` | SOA |
| HubSpot | `hubspot` | TXT |
| idCloudHost | `idcloudhost` | SOA/NS |
| Imgix | `imgix` | SOA |
| Infomaniak | `infomaniak` | SOA |
| IONOS | `ionos` | SOA |
| Keybase | `keybase` | TXT |
| KMK | `kmk` | SOA/NS |
| Leaseweb | `leaseweb` | SOA |
| Liquid Web | `liquid_web` | SOA |
| Loom | `loom` | TXT |
| MailChimp | `mailchimp` | TXT |
| Mailgun | `mailgun` | TXT |
| Mailjet | `mailjet` | TXT |
| Microsoft 365 | `microsoft_365` | MX |
| Mittwald | `mittwald` | SOA |
| Mixpanel | `mixpanel` | TXT |
| One.com | `one_com` | SOA |
| OneTrust | `onetrust` | TXT |
| OVHcloud | `ovhcloud` | SOA/NS |
| Proton Mail | `proton_mail` | TXT/MX |
| QUIC.cloud | `quic_cloud` | SOA |
| REG.RU | `reg_ru` | SOA |
| Render Better | `render_better` | CNAME |
| Saba.Host | `saba_host` | SOA |
| Sakura Internet | `sakura_internet` | SOA/NS |
| Salesforce | `salesforce` | TXT |
| Salesforce Marketing Cloud Account Engagement | `salesforce_marketing_cloud_account_engagement` | TXT |
| Segment | `segment` | TXT |
| Sendgrid | `sendgrid` | TXT |
| Sendinblue | `sendinblue` | TXT |
| SiteGround | `siteground` | SOA/NS |
| SparkPost | `sparkpost` | TXT |
| Strato | `strato` | SOA |
| Stripe | `stripe` | TXT |
| Tangled Network | `tangled_network` | SOA/NS |
| UKFast | `ukfast` | SOA |
| VentraIP | `ventraip` | SOA/NS |
| Vercel | `vercel` | SOA |
| Vultr | `vultr` | NS |
| WebHostUK | `webhostuk` | SOA/NS |
| World4You | `world4you` | SOA |
| Xserver | `xserver` | SOA |
| YalinHost | `yalinhost` | SOA/NS |
| Zendesk | `zendesk` | TXT |
| Zoho | `zoho` | TXT |
| Zoho Mail | `zoho_mail` | TXT |

## Configuration — how a client is onboarded

The agent ships with thousands of signatures, but a given client only cares about
a slice. Scoping is done with a **selection file** — a JSON list of `vendor_id`s:

```json
{ "selected": ["hubspot", "marketo", "segment", "6sense", "google_tag_manager", "..."] }
```

The loader honors it (`load_library(selection=…)`), so the matchers, the
`stats`/`scan` CLI, and the HubSpot run all operate on just that subset. Scoping
is also a big speed win (65 vendors vs 7,500) and reduces false positives.

### The configuration agent

The **configuration agent** turns a plain-English client brief into a
`selection.<client>.json`. It reads the taxonomy in this document and chooses the
`vendor_id`s that matter for that client. It is the automation layer on top of the
selection seam (today selections are hand-authored; the agent generates them).

**What the agent needs in its prompt:**

| Input | Why it matters |
|---|---|
| **Client profile** — who they are, what they sell | Anchors which categories are relevant (e.g. a CDP vendor cares about *Customer data platform* + *Analytics* + *Tag managers*). |
| **ICP / target accounts** — industry, size, region | Picks the right tier of tools (enterprise vs SMB, ecommerce vs B2B SaaS). |
| **Named competitors & "replaces" targets** | Forces those exact `vendor_id`s into the selection so the client can spot displacement opportunities. |
| **GTM motion** — PLG / sales-led / ABM / ecommerce | Weights buckets: ABM → intent/visitor-ID; ecommerce → Klaviyo/Shopify/reviews; PLG → product analytics. |
| **Domains/categories of interest** from the taxonomy | Lets the agent include whole categories wholesale (e.g. "all of *Advertising* + *Tag managers*"). |
| **Must-have / must-exclude vendors** | Hard constraints the agent honors verbatim. |
| **Precision vs recall preference** | Narrow marquee set vs the full long tail of a category. |
| **Render budget** (speed vs JS-global recall) | Whether to enable always-render (catches runtime-injected tools, slower). |

**Example prompt:**

> "Configure for **Acme**, a B2B revenue-intelligence platform selling to RevOps
> at mid-market SaaS. Competitors: Gong, Clari, Salesloft, Outreach. ABM motion.
> I care about CRM, marketing automation, CDP/analytics, ad pixels, and
> sales-intent/visitor-ID tools. Must include 6sense, Demandbase, ZoomInfo.
> Precision over recall. Optimize for JS-global recall (render on)."

**Example output** (`selection.acme.json`):

```json
{
  "client": "acme",
  "render": "always",
  "selected": [
    "salesforce", "hubspot",
    "marketo", "pardot", "hubspot",
    "segment", "rudderstack", "google_analytics", "amplitude", "mixpanel",
    "google_tag_manager", "google_ads", "facebook_pixel", "linkedin_insight_tag",
    "6sense", "demandbase", "zoominfo", "gong", "salesloft", "outreach",
    "clearbit_reveal", "leadfeeder", "warmly", "koala", "qualified", "chili_piper"
  ]
}
```

Run it: `SELECTION_FILE=…/selection.acme.json ALWAYS_RENDER=true python -m src.cli run <LIST>`.

## Appendix A — full vendor enumeration

Every vendor in the library, grouped Domain → Category. ★ = curated. Collapsed by domain; expand to read.

<details>
<summary><b>Sales & CRM</b> — 443 vendors</summary>

**CRM** (255): Agile CRM, Aidbase, Airship CRM, Aiva, Alumni Channel, Amilia, amoCRM, Anexis, Anthology Encompass, Apodle, Arketa, Armin, Arnica, AroSoftware, Astute Solutions, Automabots, AutoVitals, Avizi, Backbase, Batchbook, Beddy, Bettermode, Bevy, Bigin, Bitrix24, Bnovo, Bomb Bomb, Bonsai, Bookboost, Bookster, Bowtie, Brivity, Buz Club, Capsule CRM, CAPYS, CareCloud, Caremerge, Casafari, CDK Global, Centium, Chefpreneur, Civic Champs, CiviCRM, CleanCore, Clevy, ClinicSense, Clio, Conexa, Convert and Flow, Cosmedcloud, CRM+, CRMBOOST, Daktela Omnichannel, Datascape, Demandforce, DenGro, Deskero, Didar, Dito, Dixa, Docket, DoorLoop, DX1, EasyBroker, Edrone, Elenore, Ellucian CRM Recruit, Elromco, Entresoft, Erxes, eShopCRM, EspoCRM, EZLynx, Facilita, FlareLane, Fleetee, Flipping Pro CRM, Fluro, Follow Up Boss, Freshworks CRM, Fullbay, Fuzey Channels, Gallabox, Gestim, Giveffect, Gloo, GlueUp, Gorilla Dash, GreenRope, Hapana, HappyFox Helpdesk, Helpwise, Hesk, Hi Platform, HiBob, Hikari CS, Hiver, Hoowla, Hubtiger, ICE, Infor, Insightly CRM, Iteras, Join It, Jonas Club Software, Keap, Kenect, Kicksite, Kintone, Kundo, KVCore, Lasso CRM, Lawmatics, Laylo, Lead Generated, LeadChat, Leadific, LeadSimple, LeanData, Lenus, LEVERADE, Ligna, Liine, Linear, Mashore Method, Mazrica, MDS Brand, MembershipWorks, Mico, Mimiran, Mintox, Mirai, Molin AI, Moyklass, MRI Box and Dice, MRI Eagle, MyAlice, Neon CRM, NOCNOK, NoPaperForms, Northstar Club Management, OperateBeyond, Pepper Cloud, Percy, Perfect Storm, Perfex CRM, Phorest, Pico, Pilera, Piperun, Plait, Plannit, Plutio, Podio, Popcorn CRM, Popmix, Power CRM, Practice Perfect, Praedium, ProdPad, Profeat, Property Shell, PropFlo, Proposify, Prostoy, Proto AICX, PTminder, Pubfunnels, Q4, Qomon, Rapid Active CRM, RE-OS.com, Rent Syst, RentCafe, REsimpli, Reviews Up, Richpanel, Rinsed, Roller, Rollick, Rubic, Saabu, SabeeApp, SalesCandy, Salesforce Desk, Salesforce Experience Cloud, Salesforce★, Salesmachine, SalesMatch, Salespype, SAP, SberCRM, Sellsy, ServiceCore, ServiceM8, Sherlock, Showdigs, Sierra Interactive, Simbla, Sinch, Slate, SM Sold, SniperCRM, Soffront CRM, SoftwareSuggest, SolutionReach, Sonar, SOTA CRM, Spektrix, Spoki, Sprinklr, Spruce, StoragePug, Store Vantage, Strolid, Subscribfy, SuiteCRM, Swapcard, Swat.io, Talentegy, TDO Software, TeamUnify, Tebra, Tender Support, Tessitura, Textline, Tiled, Tint Wiz, Top Producer, TravPRO, TRIBUS, Tula, Twyne, Universe Soft, Unless, Uplifter, Vantaca, vcita, Veloce, Velocify, Vepaar, Virtuagym, Vtiger, Wabi, Wati, Wise Agent, Wodify, WoowUp, Workadu, Workbooks, Workday, WORKetc, YogaTrail, Zenu, Zoho

**Customer data platform** (54): Able CDP, Acquia Customer Data Platform, Adobe Experience Platform Identity Service, Antsomi CDP 365, Aptania, Asapp, Bandwango, BlueConic, Bread & Butter, ChurnZero, CleverData, Cooladata, Custobar, Datatrics, Exponea, FirstHive, Fueled, Fullpath, Gravito, Hull, inSided, Insider, Klaviyo Data Platform, Leadspace, Lexer, Lytics, Merge, mParticle★, Netcore Cloud, Optimove, Pinpoll, PriceSpider, Raaft, Registria, Rocket Tools, Rudderstack★, SALESmanago, Segment★, Segmetrics, Simon, Sirdata, Sitecore Engagement Cloud, Skeepers, SmartDX, Spotler Activate, Squeezely, Stibo, Sub2Tech, Tail, Totango, Treasure Data, Unito Hub, Wootric, Zeotap

**Appointment scheduling** (129): A2Z Events, Acceptd, Acuity Scheduling, AddEvent, Agendize, Aimy, Allbookable, Appointedd, Appointo, Appointy, Arlo, AutoOps, BLiNK AI, Bookafy, BookBanket, Booked, Bookeo, Booker, Bookero, Bookitit, Booklux, Bookly, BookVisit, Booxi, Boulevard, Bsport, CalendarHero, CalendarWiz, Calendly, Calenso, Cfixé, Chili Piper, ClassCreator, ClassFit, Client Diary, Cloudbeds, Counseling Kit, Cvent, DearDoc, Doctena, DrChrono, EasyWeek, eola, Etermio, Eventlink, EventOn, Evvnt, ezyVet, Fieldd, Fitssey, ForeUP, Fresha, Full Slate, FullSeats, GBooking, GetYourGuide, GlampManager, Glofox, GOrendezvous, GReminders, HotDoc, Housecall Pro, iClose, Jameda, Kalix, Limecall, Mainboard, Makeplans, Mangomint, Matchi, Meetup Express, Mews, MIYN Online Appointment, Momence, Momice, Motion, MyTime, Need Street, NightsBridge, Nookal, Occasion, Otto, Periodic, Planfy, Planway, Pluralo, Practo, Recras, Resova, RideBits, Salonist, SavvyCal, Sched, ScheduleAnyone, Shore, SimplyBook.me, Sirvoy, Skedify, Slotti, Smile Virtual, Sonline, Squire, StyleSeat, SuperHote, Swoogo, SynBird, TeamUp, TerMed, theCut, TimeTap, Timify, Timma, TravelJoy, Trumba, TuCalendi, Vagaro, Vello, Wherewolf, Whova, X.ai, Xtime, YachtSys, YoPlanning, Zen Planner, Zenbooker, ZenMaid, Zenoti, Zocdoc, Zozi

**Sales engagement** (5): AiSDR★, Factors.ai★, G2★, Outreach★, Reo.dev★

</details>

<details>
<summary><b>Marketing Automation & Messaging</b> — 728 vendors</summary>

**Marketing automation** (499): 6sense, 7moor, Acquia Campaign Factory, Act-On, Actito, ActiveCampaign, Adabra, Adenzo, Adtriba, AgentFire, Agillic, AI LOG, Aimbase, Aimerce, Aimtell, Airship, AiTrillion, Akero, Alimama, AllClients, Alohome, Amped, Ampry, Angler AI, ArtPlacer, AttractROI, Autoketing, Automated Growth, AutomateWoo, Automatic Members, AutomaticSales, Automizely, Autopilot, AvidAI, Aweber, Banana Splash, Bant, Batch, Beacons, Beam Impact, Beeketing, Bench, Bento, Birdeye, Black Crow, Blendee, Blotout EdgeTag, Blue Corona, Bluecore, Boberdoo, Boei, boomtime, Bothive, BowNow, Brafton, Brainlead, Branch, BrandBuilderAI, Braze, BrightInfo, Bronto, BTOLEAD, BuzzBuilder, BySide, Campaign Monitor, CartKit, Carts Guru, CasaSoft, Catylist, CausalFunnel, Certishopping, CHIIRP, Chimpify, CINC, Clarivoy, Claspo, Clearlink, CleverTap, ClickDimensions, ClickFunnels, Clientify, CLIKdata, Closing Boost, Cnvert, CoCo AI, COCON, Conduze, Connectally, Conneqto, Connexity, Constant Contact, ContactUs, Convead, Converge, Convertcart, Convertful, ConvertKit, Convincely, Convious, Cool Popup, Copernica, Copilot AI, Creaitor, Create Demand, CRM Done Better, CTRWOW, Curaytor, Customer Stories, Customer.io★, CXDP, D.Engage, Dakno, Dashly, data nugget, Datacrush, DataDojo, Datalitics, Datarize, DatHuis, Deadline Funnel, Deal.ai, Deep Lawn, DeepMarkit, Delera, Delivra, Dialog Insight, Doctor.com, Dotdigital, Dreamdata, Drip, e-goi, Ecal, EcomX, Edugram, Eggflow, Eloqua, Emanda, Emarsys, Ematic Solutions, emBlue, Emotive, Engaga, Enkod, eSputnik, Estate Track, eTrigue, Evidence, Evolok, ExitIntel, Feathr, Feedify, Fello, Firepush, Flable, Flodesk, Flowbox, FlowTrack, FMG Suite, Fohr, Fomo, Formtoro, Forsant, Frederick, FreedomKit, Frizbit, Frosmo, Funnel Science, FunnelCockpit, Funnels of Course, Funnelytics, Futy, Gamooga, Geggio, Genesys Cloud, Genoo, Getback, Getgabs, GetMoreStudents, GetResponse, Gleam, Goat Systems, GoodAPI, Grade.us, Grin, Grivy, Groove.cm, Growave, GrowSurf, Gruvi, Happy Talk, HappySync, Harafunnel, Hibu, Higher Logic, HighLevel, Homebot, Homefiniti, Hub Platform, Hubilo, HubSpot★, Hushly, Hyperia, Icegram, icomm, icomm - Notifications Hub, Ifdo, Influence, Informa Markets, Integrately, Interago, Intice, Invoca, Iterable, Izooto, Jabmo, Kamozi, Kartra, Kasika, KeaBuilder, Keymailer, Keywee, Kiliba, Kit, Kizen, Klaviyo★, KlickPages, KlickTipp, Kliken, Knock, Kochava, Kommi, KUKUI, Kulea Marketing, Kwanko, Kwanzoo, Lead Concept, Lead Prosper, LeadByte, Leadferno, Leads2b, LeadsBridge, LeadScore, LeadsLeap, LeadSlide, Leadsquared, Leanplum, Linda, Linkfire, Linkz, Listrak, LocaliQ Live Chat, LocalSignal, Lofty, Loops, LotLinx, Lunio, Maatoo, MadKudu, Maestra, Magnews, Maguru, MailChimp, Mailocator, Mailshake, MAJIN, ManyChat, ManyContacts, Markate, MarketHero, Marketify, Marketo★, Mautic, Maxemail, MDirector, Mega, Mentad, Merit, MessageGears, Mindbox, MissionSuite, Moast, MoEngage, Mokini, Monetize Pro, Monocle, Moosend, Mopro, Movylo, MyEsalon, Najva, NET-RESULTS, Netdeal, Nexxtmove, Niice, Notifly, Nudgify, Nurture, Nurture Boss, Oddcast, Omacro, Ometria, Omnikick, Omnisend, OneSignal, Online Succes, Opesta, Ops Calendar, OptinMonster, Optinopoli, Orimon.ai, Ortto, OtterText, Outfunnel, Outplay, Overloop, Package.AI, Papirfly, Passle, PathFactory, Persona.ly, Phonexa, PiAds, Pimster, Pixel Motion, Placester, Platformly, Plezi, Plices, Pliek, PlusThis, Pocus, Popify, Poppins, Poptin, Post Dolphin, Postie, Postscript, Privy, Probance, Profit Lifter, ProfitFlo, Progreda, Promio, Promo AI, Proofdy, PushAlert, PushBots, Pushe, PushEngage, Pushify, Pushnami, Pushouse, PushOwl, Pushpad, PushPushGo, Quizitri, Ramper, RD Station, RE:Guest, ReadyPlanet, Redrive, Rela, Releva, Remedo, Resultify, Reunion Marketing, Reuzenpanda, RevTrax, Ringostat, RiteKit, Roas Funnels, Robarov, Robly, Rockerbox, Roof, Roojoom, Rosana, Sailthru, Sales Auotomator, Salesforce Marketing Cloud Account Engagement, Salesforce Marketing Cloud Account Engagement (Pardot)★, Salesloft★, SalesWings, Sare, Satori, ScoreApp, SeedGrow, Selligent, SEMrush, Send, SendHeap, Sendinblue, Sendlane, SendPulse, SendX, Sensor Tower, SEO Samba, Setrow, Shanon, SharpSpring, ShopiMind, Signal, Signalayer, Signalize, Simplero, SimplyCast, Sleeknote, SlickText, Smaily, Smart Analytics, Smartpoint, Socedo, SOCi, SocialLadder, Sokrati, Solitics, Sophi, Spectate, SPREAD, Springbig, SprintHub, SqualoMail, Stampede, Steer Health, Storylane, Streamlyne, Stylitics, SuperBuzz, Surfside, Swifty, Synamate, Systeme.io, Systems Accel, Tagnology, Tapstream, Terminus, Text Marketer, Textmagic, The AdsLab, theMarketer, ThoughtMetric, TIEIT, TINT, tinyAlbert, TITANPush, Tolstoy, Tomi.ai, Tomis, ToneDen, Topline Pro, Tracify, Tradable Bits, Truepush, Trumpia, TrustLock, Trustmaker, TrustPulse, Unipag, Upsales, UpScale Systems, Upstack Data, Vaven, Verfacto, Vero, Vimos, Vioma, Vizury, VNN Sports, Voltn, Vuture, VWO Engage, Vyve+, Warmly, Web4Realty, WebEngage, Webinaris, Webpushr, Wheel of Popups, Wheely Sales, Wicked Reports, Wigzo, Wishloop, Wolfeo, WooChat, Woorise, Wunderkind, Wyng, Xtremepush, Yeps, Yotpo SMSBump, YouLead, Zapnito, Zaxaa, Zenrez, Zeppelin, Zevioo, Zipleads, Zotabox, Zurple

**Email** (34): Amazon SES, Aument, Benchmark, BIGLIST, Clearout, CleverReach, Doppler, Emaileri, EmailJS, Envoke, Goodbits, iEntry, INBOX, Knak, Listagram, LiveIntent, MageMail, Mailercloud, MailerLite, Mailgun, Mailjet, Mailman, Mailmunch, Salesforce Marketing Cloud Email Studio, Selzy, Sendgrid, Sendloop, Sendtex, SmartEmailing, SmtpJS, SparkPost, Upscribe, Xverify, Zoho Mail

**Webmail** (13): Apple iCloud Mail, CrossBox, Google Workspace★, Microsoft 365★, Open-Xchange App Suite, Outlook Web App, Proton Mail, RainLoop, RoundCube, SquirrelMail, Sympa, Zadarma, Zimbra

**Cart abandonment** (16): CareCart, CareCart Cartly Abandoned Cart Recovery, CartBot, CartHook, CartRocket, CartStack, GetRooster, Keptify, OptiMonk, PushOwl Web Push Notifications, Recapture, Recart, SpurIT Abandoned Cart Reminder, SweetHelp, UpSellit, Uptain

**Loyalty & rewards** (40): 99minds, Antavo, Appstle, Beans, BON Loyalty, Captain Up, CleverInsight, Eber, Fondue, Gameball, Glow, HeyPongo, Inveterate, Kangaroo Rewards, Lily, Loloyal, Lootly, Loyalis, LoyaltyLion, Loyalzoo, Loyoly, Marsello, MyCred, Nift, Piggy, Pobuca, PunchTab, Redonner, Rise.ai, Sessionly, ShopHub, Smile, SpurIT Loyalty App, TapMango, Thanx, Voucherify, Vyper, Warply, Yotpo Loyalty & Referrals, Zinrelo

**Referral marketing** (23): Aklamio, Ambassador, Buyapowa, CloudSponge, ContextBar, Coopt, EarlyParrot, Extole, Flocktory, Friendbuy, Guuru, Indi, Mention Me, Peachs, Profity, Refericon, Referral Rocket, ReferralCandy, SaaSquatch, Sharpay, SparkLoop, Viral Loops, Zuberance

**Affiliate programs** (62): A8.net, AccessTrade, Admitad, Affilae, Affiliate B, Affiliate Future, Affiliatly, Affilio, Affilo, Amazon Associates, AWIN, Backstage, Booking.com, Cellxpert, Clickbank, Convertiser, CPABuild, Digistore24, Dovetale, Duel, eBay Partner Network, eBay Store, Effiliation, Evermos, FinanceAds, FirstPromoter, GoAffPro, Hotmart, Impact, JANet, Klook, LeadDyno, Line2, Moshimo, Narrativ, Optimise, OSI Tracker, Partner Driven, Partnerize, Partnero, PartnerStack, Pepperjam, Pixeleze, Post Affiliate Pro, Rakuten, Reditus, Refersion, RevenueHunt, Rewardful, ShoutOut, Skimlinks, Social Snowball, Sovrn//Commerce, Tapfiliate, The Rave, Tolt, Tradedoubler, TravelPayouts, TSA Commerce, Upfluence, ValueCommerce, Webgains

**Fundraising & donations** (41): ActBlue, AlumnIQ, Arreva, BackerKit, Blackbaud CRM, BRYNK, Classy, Click & Pledge, Community Funded, CustomDonations, Donorbox, DonorPerfect, EveryAction, Frontstream, Fundraise Up, FundRazr, Funraise, GiveCampus, GiveSmart, GiveWP, GivingFuel, Golden Volunteer, Harness, iRaiser, Kindful, Kiva, MineLabz donations, Network for Good, OneCause, Optimy, Pushpay, Qgiv, RaiseDonors, Raisely, Resupply, Revv, Thrinacia, Twingle, Vanco Payment Solutions, Virtuous, Yapla

</details>

<details>
<summary><b>Advertising & Tag Management</b> — 240 vendors</summary>

**Advertising** (211): 33Across, Aarki, AcuityAds, AD EBiS, Ad Lightning, Adalyser, Adara, AdBridg, Adcash, Adex, Adform, ADFOX, AdGlare, AdInfinity, Adition, Adloox, Admixer, Admo.tv, Admost, Adnegah, AdOcean, Adomik, AdRecover, AdRiver, AdRoll, AdScale, AdThrive, Advally, Advert Stream, Adverticum, Amazon Advertising, Amobee, Anetwork, Aniview Ad Server, Anura, AnyClip, Appier, APPLOVIN, AppNexus, ArcSpan, Assertive Yield, Audiohook, Automatad, Basis Technologies, Beeswax, Bidmatic, BittAds, BlokID, Broadstreet, BuySellAds, Carbon Ads, Chitika, Clickaine, Clickbrainiacs, ClickFreeze, ClickGUARD, Clicktripz, Cluep, Collective Audience, Concert, Container Media Group, Criteo, Dable, DanAds, Dealer Spike, Dianomi, District M, Dolead, DoubleClick Ad Exchange (AdX), DoubleClick Campaign Manager (DCM), DoubleClick Floodlight, DoubleClick for Publishers (DFP), DoubleVerify, DTScout, DynAd, Epom, eRate, EthicalAds, Excel Impact, Exit Bee, ExoClick, Facebook Ads, FastTony, Felmat, FirstImpression.io, FreakOut, Fusion Ads, Geniee, GenieWords, Getintent, Google AdSense, Google Ads★, Google Publisher Tag, GumGum, Hashtag Labs, Header Bidding Ai, HypeLab, i-mobile, ID5, Index Exchange, Infolinks, Innervate, Innovid Advertising Measurement, Integral Ad Science, Internet Brands, JuicyAds, Kevel, Klickly, Kueez, Leadbit, Linkedin Ads, LiveRamp DPM, LKQD, MadAdsMedia, Magnite, MainAd, Manatee, Mantis, Media.net, Mediavine, MGID, Microsoft Advertising, Mile.tech, MNTN, Mountain, Nativo, Nextdoor Ads, OneTag, ONiAD, Open AdStream, OpenWeb, OpenX, Pinterest Ads, Placed, Podsights, Prebid, Premion, Primis, Project Wonderful, PubGuru, Publy, PubMatic, Pubstack, PurpleAds, Pushub, Q1Media, Qbrick, Quon, Rakuten Advertising, Raptive, Reddit Ads, Relap, RevBid, RevContent, RevJet, Rontar, Rubicon Project, SabaVision, Sharethrough, SHE Media, Simpli.fi, Sixads, Sizmek, Smart Ad Server, Snap Pixel, snigel AdEngine, Sonobi, Sortable, Sovrn, SpotX, StackAdapt, STN Video, Sublime, Swoop, Taboola, Tagtoo, Tapad, Tapsell, Tatari, Teads, The Arena Group, The Monetyzer, theTradeDesk, Thor-Media, Titan, TrafficGuard, TrafficStars, TripleLift, TVSquared, Twiago, Twitter Ads, Unruly, Upravel, Utiq, Valuad, VDX.tv, Veoxa, Verizon Media, VerticalScope, Vidazoo, Wazimo, Webica, Wehaa, WiderPlanet, WordAds, Yahoo Advertising, Yandex.Direct, Yektanet, Yieldlab, Zanox, Zeus Technology

**Retargeting** (18): Blue, Captify, Cross Pixel, Fixel, Linx Impulse, Meazy, Notix, PebblePost, Picreel, Revenue Roll, RTB House, SharpSpring Ads, Smarter Click, Socioh, Squadata, SteelHouse, Struq, Uzerly

**Tag managers** (11): Adobe DTM, Adobe Experience Platform Launch, Commanders Act TagCommander, Ensighten, Facebook Pixel Advanced Matching, Google Tag Manager, Matomo Tag Manager, TagPro, Tealium, Yahoo! Tag Manager, Yottaa

</details>

<details>
<summary><b>Analytics & Optimization</b> — 780 vendors</summary>

**Analytics** (397): 51.LA, 52Degrees, Abralytics, Acecounter, Ackee, Acoustic Experience Analytics, Acquia Personalization, Actirise, AdCalls, Adjust, Adline, Adobe Analytics, Adtribute, Ahoy, Air360, Airbridge, Akavita, Albacross, Alexa Certified Site Metrics, Alloka, Allstate, Alpharank, Amplitude★, Analysys Ark, Analytick, AnalyticOwl, AnalyticsConnect, Analyzati, Analyzee, Analyzz, AppDynamics, Appsflyer, AT Internet Analyzer, AT Internet XiTi, Attribution, Auryc, AutomatePro, Avanser, AvidTrak, AWStats, Azure Monitor, Baidu Analytics (百度统计), Baremetrics, Bazo, Better Replay, Beusable, Biano, BizSpring, Black Book, Blueshift, Browsee, BugSnag, Burst, Cabin, CaliberMind, Call Cap, CallRail, CallRoot, CallTrackingMetrics, Capturly, Carrot quest, CARTO Data Observatory, Castle, CatchJS, ChannelAdvisor, Chartbeat, Clearbit Reveal, ClearSale, ClickHeat, ClickTale, Clickx, Clicky, Cloudflare Browser Insights, CNZZ, comScore, Contentsquare, Converdiant, Conversio, ConvertFlow, Cookie Assistant, Countly, Crazy Egg, Critical Mention, Cux, Databuddy, DataMilk, Datanyze, Decibel, Delacon, Dema, Demandbase, Deriv, Detectizr, Dexem, Dynatrace, ECBB, EcomScout, Econda, Elastic APM, Elevar, Enecto, Engagio, Enquisite, Errorception, Etracker, Everflow, Everviz, ExactVisitor, ExtraWatch, Ezoic, Facebook Pixel, Fastbase, Fathom, FC2 Analyzer, Finalytics, FindGore, Fireside, Flurry Analytics, Freespee, Friendly Analytics, FullContact, FullStory★, Gator, Gauges, Gemius, Glassbox, GoatCounter, Gong, Google Ads Conversion Tracking, Google Analytics Enhanced eCommerce, Google Analytics★, Google Call Conversion Tracking, GoSquared, GoStats, Grafana, Graphly, GreenStory, GrowingIO, hantana, Heap★, Heeet, Highlight.io, Histats, HockeyStack, Hotjar, Hubalz, Huberway Analytics, HubSpot Analytics, Humblytics, Hyros, IBM Coremetrics, Iconosquare, INFOnline, InMoment, Insignal, Inspectlet, Instana, ip-label, Jarvis Analytics, Jirafe, June, Juvo Leads, Kilkaya, KISSmetrics, Koala, Konget, Kount, Kwai pixel, Lead Forensics, LeadBoxer, Leadfeeder, LEADIN, Leadinfo, LeadsSight, Leady, LeaseHawk, Lexity, Linkedin Insight Tag, LinkMink, ListTrac, Litmus, LiveBy, Liveinternet, LiveSession, Logaholic, Loggly, Loglib, LogRocket, Looker, Lucky Orange, Luigi’s Box, Lumino, Lumio, Mapp, Marchex, Marfeel, MarketPlan, Massflow, Matomo Analytics, Measured, Medallia, Mediahawk, Meltwater, Metrics Key, MetricsCube, Metrilo, Microsoft Clarity, Microsoft Power BI, Mint, Mixpanel★, Modio, Monitus, Monsido, Moostik, Mouse Flow, Mux, MyStat, Navegg, Naver Analytics, Nemu, Neowize, Nepcha Analytics, Netvibes, NexMind, Nimbata, NinjaCat, Nocodelytics, Noddus, Northbeam, OneStat, Open Web Analytics, OpenPanel, opentelemetry, Opentracker, Oracle Infinity, Oracle Moat Measurement, Oracle Recommendations On Demand, ostr.io, Panelbear, Parse.ly, Pathful, Patient Prism, PatientLoop, PayPal Marketing Solutions, Peftrust, Pendo, Peripl, Piano Analytics, Pinterest Conversion Tag, Piwik PRO Core, Plausible, Plerdy, Podkite, Polar Analytics, PostHog, Powster, PrimeGate, Profitwell, Proof Factor, Psyma, Publytics, Pubperf, Pyze, Qooqie, Quantcast Measure, Quantum Metric, Quora Pixel, Quotemedia, Rambler, Reactful, Realytics, Refix, Reinvigorate, Repro, Resonate, Reverse Market Insight, Ringba, Riskified, riyo.ai, Roistat, Ronin Sport, Ruler Analytics, Rybbit, S&P Global Mobility, SalesReps.io, SalesViewer, Say.ac, SealMetrics, Seeda, SegmentStream, Seline, Sensai Metrics, Sensors Data, Sentifi, Session Rewind, SessionStack, Setrics, ShinyStat, Sift, Signifyd, Simple Analytics, Sirge, Sistem, Site Kit, Site Meter, Sitefinity Insight, Siteimprove, SiteVibes, Skai, SkyGlue, Slingshot, Smartlook, Smartocto, SniffURL, Snoobi, Snowplow Analytics, Spectro, Spinnakr, Splitbee, Spotzi, Sprocket, Stack Analytix, Statcounter, Statsig, Stetic Analytics, SuperPluralAnalytics, SuperStats, Swagify, Sweet Analytics, Swetrix, Syndeca, Synerise, Tableau, Tallentor, Task Analytics, Tencent Analytics (腾讯分析), Tend, TG Track, ThankYou Analytics, The Hotels Network, Thesis, TikTok Pixel, Tinybird, Topic Intelligence, Trackbee, Trackboxx, TrackFox, TrackJs, trackthemetric, Traek, Trak, Triple Whale, Trovit, Twitter Analytics, UI Avenue, UMAI, Umami, uMarketingSuite, Useberry, user.com, UXSniff, Varos, Ve Global, Veonr, Vercel Analytics, Vercel Speed Insights, VersaTailor, Vicomi, Vidora, VisitorVille, VK Pixel, VWO, W3 Ataiva, W3Counter, Wask, WatchThem, Web CEO, Weberlo, Webeyez, WebMetric, WeboLead, Webolytics, WebSTAT, Webtrends, WildJar, Wipe Analytics, Wisetracker, Wonder, Woopra, WP-Statistics, Xzero Analytics, Yahoo! Web Analytics, Yandex.Metrika, Yxper, Zentap, Zipkin, Zoominfo

**RUM** (18): Akamai mPulse, Amazon CloudWatch RUM, Atatus, Datadog, Dynatrace RUM, Eggplant, Microsoft Application Insights, New Relic, Pingdom RUM, Quanta, Raygun, Rumvision, Sematext Experience, Site24x7, SpeedCurve, Splunk RUM, Uptrends, Wakav Performance Monitoring

**A/B Testing** (40): AB Tasty, ABLyft, Adobe Target, Bringie, Bunting, Complianz, Convert, Dexter, Dynamic Yield, Estore Compare, Google Optimize, GrowthBook, Intelligems, Intellimize, Juo, Kameleoon, Karte, Monetate, Neat A/B testing, Nelio Testing, Omniconvert, Optibase, Optimizely, Oracle Maxymiser, Overheat, Pretty Damn Quick, Ptengine, RankScience, Shoplift, SiteSpect, Split Hero, Talkable, Tontine, Trbo, Trident AB, UserZoom, Varify, Vertster, VisiOpt, Zoho PageSense

**Personalisation** (143): 4-Tell, Adaptix, Adnymics, Adoric, Apptus, Attentive, Barilliance, Beyable, bluebarry, Blueknow, Bold Commerce, Bounce Commerce, BrainSINS, Breinify, Cartful, Cerkl, Clerk.io, Clinch, CloudEngage, Clubcast, Combeenation, Connectif, ConvertBox, Cordial, Crall, CREMA, Cross Sell, CustomFit, Customily, Cxense, Dapta, Darwin Pricing, Depict, Dialogue, Drapr, DreamROI, Epoq, Fanplayr, Findmeashoe, Fit Analytics, Fitizzy, Fitle, Fresh Relevance, Glami, Groobee, Hello Retail, HulkApps Infinite Product Options, iGoDigital, Jeeng, Jivox, Jubna, Justuno, Kaisa, Kibo Personalization, Kiwi Sizing, LiftIgniter, LimeSpot, Lumise, Mezereon, Movable Ink, Mutiny, Navu, Nosto, Nuqlium, Outfindo, Ownpage, PageNudge, ParticularAudience, Peerius, PersonaClick, Personizely, Personyze, Perzonalization, Piano, Poloriz, Potions, Prediggo, Preezie, Primeleads, Printful, Printlane, Prooven, Provely, PureClarity, Qstomizer, Qubit, Raptor, Rebuy, Recolize, Recombee, RecoverMyCart, Reelevant, Reflektion, Relewise, Retail Rocket, Revieve, RevLifter, RichRelevance, RightMessage, Rokt, Rtoaster, Ryzeo, SaleCycle, SalesFire, Salesforce Interaction Studio, Samsung Food, Sendpad, Shoefitr.io, Shopbox AI, Sizebay, SizeMe, Skeep, SmartHint, Storyly, Strands, Streamoid, StrutFit, Systema, Syte, Tagalys, Target2Sell, Teeinblue, Things Solver, Trendemon, Triggerbee, True Fit, Twik, Unbxd, Upsy, Usizy, VerifyPress, Virtusize, Visitor.js, Vue.ai, Wair, Webeo, Webyn, Wiqhit, WiserNotify, Wishi, XGen Ai, Yieldify, Zakeke

**Segmentation** (8): Adobe Audience Manager, Bloom Labs, Omeda, Oracle BlueKai, Poltio, Salesforce Audience Studio, Tealium AudienceStream, Viafoura

**Surveys** (43): Bestie, Brandquiz, Clicktools, coUrbanize, Crowdsignal, CustomerSure, Delighted, Doorbell, EasyPolls, Emojicom, Enalyzer, FeedbackAutomatic, Guest Suite, GuildQuality, Hotjar Incoming Feedback, HulkApps Form Builder, Impressure, Informizely, Iterate, KnoCommerce, Marquiz, Mosio, OpinionBar, OpinionLab, Poll Everywhere, Pollster, Pulse Insights, Qualaroo, Qualitando, Qualtrics, Recommy, Refiner, Riddle, Segmanta, Service Management Group, SimpleSat, Sprig, Survicate, Tally, Typeform, Userback, Wufoo, Yay! Forms

**User onboarding** (18): Appcues, Arengu, Canopy Connect, Chameleon, Checkin, Elevio, FintechOS, Hansel, LOU, PeerPal, Poper, Stonly, Toonimo, Userflow, Userlane, Userpilot, WalkMe, Whatfix

**SEO** (35): Ahrefs, All in One SEO, All in One SEO Pack, Alli, Atomseo, Attracta, Auto HQ, BlogHunch, BrightEdge, BrightLocal, ePublishing, Farazi Bilişim, Huckabuy, Linguana, Mieruca, Nowfloats, On The Map, Realist, RioSEO, Schema App, SEOAnt, SEOmatic, SEOmator, SEOPress, SiteBooster, Spotzer, Submit Express, Synup, The SEO Framework, Whitespark SEO, WordLift, WP SEO AI, Yoast SEO, Yoast SEO for Shopify, Yoast SEO Premium

**Content curation** (36): Bazaarvoice Curation, Ceros, Cevoid, ContentBot, ContentGems, Contently, Contents, ContentStudio, Covet.pics, CPEx, Curated, Emplifi UGC, FeedMagnet, Foleon, Foursixty, Frase, Juicer, Klangoo, Line-Up, MadCap Software, Miappi, Natural Intelligence, Nosto Visual UGC, Octipulse, Olapic, Photoslurp, Pixlee TurnTo, Postano, Rock Content, Scoop.it, SnapSea, Sniply, StoryStream, Sverve, Tagboard, Tagembed

**Form builders** (42): Airform, Basin, Campflow, Digioh, Form.io, Form.taxi, Formaloo, FormAssembly, FormBold, FormBucket, Formcake, Formcan, FormDr, Formester, Formless, Formli, Formrun, Formsite, Formsort, Formstack, Frontlead, Google Forms, GoZen Forms, Growform, Inputflow, Jotform, Klaviyo Forms, Modal Forms, NativeForms, Netlify Forms, OpnForm, Pabbly Form Builder, Powerful Form, QForm, Quform, Reform, Respondi, Sheet Monkey, Slapform, Superform, Web3Forms, Youform

</details>

<details>
<summary><b>Customer Support & Engagement</b> — 523 vendors</summary>

**Live chat** (361): 11Sight, 42Chat, 8x8, Acquire Live Chat, ActivEngage, Ada, AINIRO, Aircall, Aivo, Akia, Alive5, AnimalChat, AnyChat, ApexChat, Apple Business Chat, Arabot, ArrowChat, ArtiBot, AsisteClick, AskSpot, Atlasmic, B2Chat, BespokeChat, BetterBot, BirdSeed, Blinger, Blip, BoatChat, Bold Chat, Boost.ai, Bot9, botBrains, Botmind, BotPenguin, Botpress, Botsify, Botsonic, Botsplash, BotStar, BotUp, Brevo, Callbell, Callgear, Capacity, CarChat24, CEMax, Centribal, Channel.io, Chaport, Chat Chasers, Chat Robot, Chatbaby, Chatbase, ChatBot, ChatBotBuilder, ChatBullet, ChatFood, ChatGen, Chatgo, Chatify, Chative, ChatLab, Chatlio, Chatlyn, ChatNode, ChatPlus, Chatra, Chatroll, Chatsimple, ChatStack, ChatThing, Chatway, Chatwee, ChatWING, ChatWith.io, Chatwoot, Chaty, Chekkit, Chord, Clearstream, ClickChat, ClickDesk, Cliengo, Client Chat Live, Coax, Cognigy, Collect.chat, CometChat, Comm100, Conferbot, ConvertoBot, Copilot.Live, CoRover, Crikle, Crisp Live Chat, CU Chat, Czater, DeskPro Chat, Desku, DevRev, Dialogity, DialogShift, Dina Kunder, DocsBot, Dotdigital Chat, DoubleTick, Drift, Droxy, Droz Bot, EasiChat, EasyLiao, eGain Conversation, eKonsilio, Element, EliseAI, Engati, Enterprise Bot, Envolve Tech, Facebook Chat Plugin, Fastmind, Five9, Flashchat, Floatbot, Flyzoo, Forethought AI, Freshchat, Frisbie, Froged, Front AI, Front Chat★, Genesys Chat, Geniee Chat, GetChat, Giosg, Gist, Gista, Gitter, Gladly, Glassix, Gleap, Gleen, Glia, Gobot, Goftino, Gorgias★, Grasp, Gravity, Groove, HappyFox Live Chat, Haptik, HelpCrunch, HelpOnClick, Hoiio, Hoory, HubSpot Chat, Huggy, iAdvize, Ideta, Ikeono, Imber, ImBox, InforUMobile, Infoset, InSyncai, Intaker, Interakt, Intercom★, iSina Chat, Jenny, Jitsi, JivoChat, Joinchat, Joonbot, Kapture CRM, Karoo Chat, Kauz, KeyReply, Klara, Knock Knock App, Krible, Kustomer, Landbot, Lead-Finity Webchat, Leadster, Leadtex, Let's Connect, Lime Talk, LimeChat, Lindy, LiveAgent, LiveChat, LiveHelp, LivePerson, LiveTex, LiveZilla, Lovi, Mainstay, Maisie, Mava, Medchat, Melibo, Merlin, MessageMedia, Mioot, MoinAI, Mottle, Moveo.AI, Muchat, MyLiveChat, Myma, Neexa, NeoAsist, Netrox, Newo, Ngage Live Chat, Ninchat, Norby, Oct8ne, Olark, Ometrics, OnChat, Ondestek, Onicon, Onlim, Online Chat Centers, OnSip, Onsite Support, OpenChat, P3chat, Pancake, Phonon, Ping Parrot, Pipedrive★, Plivo, Posh, Poster, Prosperous AI, Provide Support, Pubble, Pure Chat, Pusher, Qiscus, Qpien, Qualified, Quality Unit Help Desk, Qualva, Querlo, QuickCEP, Quickchat AI, Quicktext, Quiq Messaging, Quixchat, Rake, Raychat, Re:amaze, Re:plain, REI Chat, Replyco, Respond.io, Responsa, Retain, REVE Chat, Rispose, Robofy, RoboReception, Rocket.Chat, Rotic, Ruby Chat, Salesforce Service Cloud, Sameday, Schedule Engine, Screets, SegMate, Sharpen, Shopify Chat, SignalZen, Simla, SiteGPT, Sitehood, Slaask, Smallchat, Smartsupp, Smilee, SnapCall, SnapEngage, SnatchBot, Sobot Live Chat, Solvemate, Solvvy, Sonetel Chat, SpatialChat, Spatie Support Bubble, SpeakPipe, Spikmi, Splutter AI, Subiz, Sugester, Suiteshare, Superchat, Swell CX, Tactful, Talk-Me, Talkdesk, TalkJS, Tallentor Widget, Tars, Tawk.to, Tencent QQ, Text In Church, TheBotForge, Thinking Chat, Tidio, Tiledesk, Tolk, Tooltip, Trengo, TuoTempo, uhChat, Ultimate, Umni, Unblu Virtual Agent, UserLike, Userlink, vChat, Velaro, Venyoo, Vergic, Verloop, ViaSay, Virtual Chat, VirtualSpirits, Visitor Chat, Voizee, Warm Welcome, Webbotify, Webim, Webotit, WebQnA, Weply, WhatsApp Business Chat, Whelp, WhosOn, WidgetWhats, Wikit Live Chat, Wix Answers, WotNot, Xenioo, Xeno Chat, yellow.ai, Yomdel, Yonder, Zendesk Chat, Zendesk Sunshine Conversations, Zenvia, Zipchat, Zipteams, Zoho SalesIQ, Zoko, Zoominfo Chat, Zowie, Zulip

**Reviews** (100): Alchemer Mobile, Ali Reviews, Alpha Review, Appzi, AskNicely, Avis Verifies, Bazaarvoice Reviews, Clutch, Contlo, Customer Alliance, Famewall, FeatherX, Feefo, Fera, Fider, Flamp, FlockRocket, Frill, GetReview, GoodReviews, Google Customer Reviews, HulkApps Product Reviews, iiQ Check, Influenster, Judge.me, Junip, Klaviyo Reviews, Konfidency Reviews, Kudobuzz, Letro, LipScore, Loox, LoyaltyLoop, MoreVago, Myli, Oculizm, Okendo, Orankl, Poll Maker, PowerReviews, ProveSource, PulseM, Qualitelis, Ratesight, RealSatisfied, Reevoo, Rep.co, Repuso, Reputon, Reviefy, Review Stars, Review Wave, Reviewdoku, ReviewForest, Reviewgrower, ReviewLead, ReviewPro, ReviewRail, Reviews.io, Reviewshake, ReviewSolicitors, Rockee, Ryviu, SafeBuy, Senja, Serchen, Shapo, Shopify Product Reviews, ShopperApproved, Shoutout Testimonial, SiteJabber, SocialJuice, Societe des Avis Garantis, SoTellUs, Stamped, Tagshop, TestFreaks, Testimonial Robot, Thimatic, true, Trusted Shops, Trustify, Trustindex, Trustio, Trustpilot, Trustspot, Trustvox, U-KOMI, UGC Creative, Vizium, VocalReferences, Vouchley, VReview, Wally, WinLocal, Wiremo, Word of Mouth, Yotpo Reviews, Zoorate, Zyratalk

**Comment systems** (14): Annoto, Cackle, Commento, Cove, Disqus, Giscus, IntenseDebate, Isso, Livefyre, Question2Answer, ReplyBox, Twikoo, utterances, Vuukle

**Translation** (12): Bablic, ConveyThis, Conword, Crowdin, Easyling, langify, Linguise, Pluglin, Smartling, Transcy, Weblate, Weglot

**Accessibility** (36): AccessiBe, Accessibility Toolbar Plugin, Accessible360, Accessibly, AccessiWay, Adally, AdaSiteCompliance, All in One Accessibility, Allyable, Allyant, AudioEye, digi·access, Droxit, Enable, EqualWeb, eSSENTIAL Accessibility, Facil-iti, Handtalk, HikeOrders, Level Access, Magixite, Make-Sense, Marshal, Nagich, NagishLi, Piman, Pojo.me, Poloda AI, Recite Me, Silktide, Texthelp, uRemediate, UsableNet, User Accessibility, UserWay, Voice Intuitive

</details>

<details>
<summary><b>Commerce</b> — 1,376 vendors</summary>

**Ecommerce** (761): 24nettbutikk, 2ClickShop, 42stores, 4Partners CMS, 91App, Aacio, Aasaan, AbanteCart, Abicart, ABOUT YOU Commerce Suite, Accesso, AceShop, Activ8 Commerce, ADAPT, Adevole, Adimo, Advin, Aedi, Aero Commerce, Afosto, AfterBuy, AIMEOS, Akilli Ticaret, Akinon, AkoCommerce, AlMatjar, Amasty, Amazon Webstore, Apanio, Aphix, AppSell, AptusShop, Arastta, ARI Network Services, Artifi, Ashop, Askas, Aspin, AstraFit, ATSHOP, autoship, Avangate, Avasam, Awtomic, Azoya, Bag, Bagisto, Balance, Base, bdok, Beeshop, Better Cart, Big Cartel, BigCommerce, BigCommerce B2B Edition, Bigshop, Bigware, Bikayi, Billgang, BinderPOS, Bizweb, Blackcart, BLAZE, Bloom, BMT Micro, Bodygram, Bold Options, BookManager, Bootic, Bottle360, Boutir, Brink Commerce, Bsale, BSmart, ButterMove, Buyist, Cafe24, Candid, Cart Functionality, Cart.com, Cartera, Cartpanda, CartPops, Cartum, Carussel, CarWeb, CCV Shop, Celebros, Celerant, Centra, ChannelApe, Checkout Champ, Ciklik, CIMcloud, CitrusLime, City Hive, Clayful, Cleverbridge, CloudCart, Cloudfy, Cloudify.store, CloudSuite, Cluster CIS, CMoffer, CmonSite, Cococart, ColorMeShop, Comarch e-Sklep, Comgem, CommentSold, Commerce Engine, Commerce Server, Commerce Vision, Commerce.js, Commerce7, CommerceHQ, Commercelayer, commercetools, Commercio, Common Ground, Comms, Composite Products, Constructor, Contentder, Convertr, Corksy, Correos Ecommerce, Cosmoshop, Cova, Craft Commerce, Crealive, Crystallize, CS Cart, cStore, CubeCart, CYBERBIZ, DanDomain, DanDomain Webshop, DCKAP Commerce, Dealspotr, Destini, Desty, Devuelving, DevzCart, DialogTab, DigiFi, Digital Showroom, DigitalRiver, Direktonline, Ditto, Divide, Dokan, Dooca, DotPe, Dotser, Dotter, Drinks, Drubbit, Drupal Commerce, Dukaan, Dukany, e-Shop Commerce, E37, Eaglecart, Easol, Easy Orders, EasyDigitalDownloads, Easysize, EasyStore, ebisumart, EC-CUBE, eCaupo, ecbeing, EcForce, EcomArtists, EcomCart, eComchain, Ecommercen, Ecomtrack, Ecomz, eCShop, Ecwid, eDokan, EKM, Elastic Path, Elcodi, Elloha, Empretienda, Enabase, Ensi, ePages, Estore Shopserve, Etail Systems, Eticex, Eveho, ewiz commerce, Excentos, Exitshop, eZCater, Fabric, Faire, FARFETCH Black & White, Farmakom, Faslet, Fast Checkout, Fast Simon, Fastcommerce, FastSpring, Fastspring, FatherShops, Fbits, Feedonomics, Fenicio, FieldStack Omni, Fileflare, FlexyPe, Flipshop, Floranext, Florist Touch, Florist Window, Food-Ordering.co.uk, Forie, ForoshGostar, Fortune3, Fourthwall, Foxy.io, Freemius, freewebstore, Fresho, Freshop, FurnitureDealer, Future Shop, Fygaro, Fynd Platform, Gambio, GaniPara, Gekosale, Gelato, GEOvendas, Gesio, GetAuto, GetCommerce, GetMeAShop, GOb2b, GoDaddy Online Store, Gomag, GoodApps, GoodEshop, Goshly, GoVedia, GrandNode, Grappos, GrocerKey, GrooveKart, Growing Good, Gumroad, Happy Meal Prep, Haravan, HCL Commerce, HighStore, HikaShop, Hit-Mall, Horoshop, Hotbot, HumCommerce, Hummerce, Ideasoft, Identixweb iCart, IdoSell Shop, IFC Markets, Ikas, Iluria, iMagaza, Immerss, Importify, Impresee, Imweb, InkSoft, InnoShop, Innovorder, inSales, Intershop, Intiaro, Inventrue, Inveon, iPresta, Irroba, iSET, Itoris, J2Store, JET Enterprise, Jetshop, Jibres, JoomShopping, JShop, JTL Shop, Jumpseller, Justo, k-eCommerce, Kajabi, Kalio, Kamva, KanzOboz, Kartify, Kartmax, Kartris, Kenlo, Keyvos, Kibo Commerce, Kimonix, Kiosked, Kitcart, Kleecks, KMK, KobiMaster, Kooomo, KQS.store, Kssib, Kwipped, KYKLO, Lapis, Lazada, Leafly, Lightspeed eCom, Linx Commerce, Litium, LocalExpress, LogiCommerce, Loja Integrada, Loja Mestre, Loja Virtual, Loja2, Lojas Online CTT, Looksize, Lovingly, LPQV, Mabisy, Magazord, Magento, Maho, Makane, Maker, MakeShop, MakeShopKorea, Marcando, Matajer, Matjrah, Mattaki, Medoc, Medusajs, Mercado Shops, Merchello, Metorik, Mginex, Microsoft Dynamics 365 Commerce, Miestro, Minted, Mirakl, Miva, Mixin, Mobify, Modified, Modified eCommerce, Mojo, Mondo Media, Monkcommerce, MonoBill, Monto, Moori, Moovin, MSAAQ, MSHOP, My Food Link, MyCashFlow, MyOnlineStore, MyPlay, Nacelle, NagaCommerce, Napps, NEO - Omnichannel Commerce Platform, Neto, NetSuite, Next Basket, Next Total, Nibiru Ecommerce, Nidux, Nimbu, Nody, nopCommerce, Norce, Novel, novomind iSHOP, Nuvemshop, Nyehandel, Ochanoko, ocStore, Offset, Oleoshop, Omega Commerce, Omie, OneCommerce, OnShop, Open Classifieds, Open eShop, OpenCart, OpenTiendas, Optimizely Commerce, Oracle Commerce, Oracle Commerce Cloud, Orckestra, OrderCast, OrderMyGear, OrderPort, OrderYOYO, OroCommerce, osCommerce, Oxatis, OXID eShop, OXID eShop Community Edition, OXID eShop Enterprise Edition, OXID eShop Professional Edition, oXyShop, Packman, Palbin, Parts Square, Parttrap ONE, Pattern by Etsy, Payhip, Pear Commerce, PeckaDesign Publicator, Peddle, Peecho, Peel, PerfectBot, Phoenix Cart, PinnacleCart, Pixieset Store, PlatinMarket, plentymarkets, PlentyONE, plentyShop LTS, Plotch, Plug&Pay, Plugo, Poshmark, Posify, Poski, Powerboutique, Powergap, Premmerce, Pressero, PrestaShop, Prima Software, Programia, Projesoft, Prom, Propcart, Proticaret, PuppetVendors, PureCars, Qonnex, Qshop, Quick.Cart, Quickbutik, QuickSell, Qukasoft, Qumra, Rabfy, Radial Ecommerce, Rain, Raku-uru Cart, Rakuten Digital Commerce, RandemRetail, Reaktion, RealNex MarketPlace, RedCart, Redicom, RediRedi, RedShop, RELOOP, Remarkable Commerce, Reserva INK, Restaumatic, Retisio, Rewix, Rezku, RMZ, RND, Robin, ROC Commerce, Rocketfy, RomanCart, Saleor, Salesbeat, Salesforce Commerce Cloud, Salesnauts, Salla, Saly, Sana Commerce, SAP Commerce Cloud, SAP Upscale Commerce, Sapo, Satu, Sauce Social Commerce, Sazito, Scalefast, ScanNet Webshop, Scayle, SearchFit, Sellacious, SellBe, Sellbrite, Selldone, Sellerdeck, SellersCommerce, Selless, Sellfy, Sellingo, Sellix, SellSite, Sellwild, Selly, SEP Platform, Sharetribe, Shine Commerce, ShionImporter, Shoopy, Shop Application, Shopaholic, Shopatron, ShopBase, Shopblocks, Shopcada, Shoper, Shopery, Shopfa, ShopFactory, ShopGate, ShopGold, Shopify, Shopiteka, Shopix, Shoplazza, Shopline, Shoplo, Shopmaker, Shopmatic, Shoporama, ShopPHP, Shoppiko, Shopping Feed, Shoppub, Shoppy, Shoprenter, Shoprocket, Shoproller, ShopSite, ShopStorm, ShopStyle, Shopsys, Shoptet, Shopthru, Shoptrader, ShopVOX, Shopware, ShopWired, ShopX, Show Recent Orders, SidePanda, SIGE Loja, Sign Customiser, Simbel, Simple Goods, Simplo7, Sirclo, Sitoo, Sixshop, Sizekick, Sizey, Sky Pilot, Sky-Shop, Smartstore, Smartstore biz, SmartWeb, Smootify, Snipcart, Socital, SoftTr, Soldsie, Solidus, Solusquare OmniCommerce Cloud, Soocommerce, SoteShop, SpeedEcom, Spiffy Stores, SpiritShop, Spreadr, Spree, Sprii, Spring for creators, Spryker, Sqimple, Square Online, Squarespace Commerce, StackCommerce, Stay AI, Storagely, Storbie, Storearmy, Storeden, Storefront, StoreHippo, Storeino, Storenvy, Storeplum, stores.jp, Storrea, Styla, Subbly, Subscrimia, SummerCart, Sunshop, Swaven, Swell, Sylius, Syncee, Synctrack, T-Soft, T1 Paginas, TakeDrop, TakeTheme, Talex, TargetBay, Tauros Media, TeamSystem Commerce, Tebex, Tekion, Textalk, THG Ingenuity, ThriveCart, Ticimax, Tictail, Tiendanube, Tiendy, Tiktak Pro, TomatoCart, Toolbx, Tossdown, TotalCode, Touch2Success, TradePending, TradePro, Tradift, Transax, Tray, Tribox Ecommerce, TRISOshop, Tritac Katana Commerce, Trove Recommerce, TrueCommerce, Tulo, Twsaa, Typof, Ubercart, Ucommerce, Ueeshop, UltraCart, Unas, Unbound Commerce, Unbox, Unchained Engine, Unilog, Upgates, UpsellPlus, Uvodo, VB Media, Vendaecia, Vendio, Vendre, VentasxMayor, Versa Commerce, Vextras, Vfinder, ViArt Shop, vibecommerce, VikaOn, Vikreta, vinSUITE, VirtueMart, Visenze, Viskan, Visualsoft, Vivenu, Vnda, Volusion, Vondera, Vop, Voracio, VP-ASP, Vrio, VTEX, Wake, Wake Commerce, wap.store, Wave Commerce, Wazala, wBuy, Web Shop Manager, Webareal, Webasyst Shop-Script, Webflow Ecommerce, Websale, Webx, Weezbe, Welcart, Whitelabel MD, Wholesale Suite, Wikinggruppen, WineDirect, Wins eCommerce, Wix eCommerce, WiziShop, WooCommerce, Workarea, Workstand, WSHOP, Wx3, X-Cart, Xanario, Xonic, Xretail, xtCommerce, Yahoo! Ecommerce, Yampi Virtual store, Yclas, Yell eCommerce, Yepcomm, YM Cart, YNAP Ecommerce, Yoori, Yopify, YouCan, Youzan, Yupop, Zad, Zammit, Zapiet, Zeald, Zen Cart, ZenBasket, Zenzzen, Zepio, Zestard, Ziadah, Zid, Znode, Zoey, Zoho Commerce, Zola Planner, Zoorix, Zozo

**Ecommerce frontends** (16): Aiden, Argento, Breeze, Deco.cx, E-Com Plus, Front-Commerce, GoMage, Hyva Themes, Kickflip, Makaira, Platter, PWA Studio, ScandiPWA, Shogun Frontend, Vue Storefront, Warp Store

**Shopify apps** (142): Accentuate Custom Fields, AdNabu, Alia, Autocommerce, Autoketing Product Reviews, Avada AVASHIP, Avada Boost Sales, Avada SEO, Avada Size Chart, Back In Stock, Beam AfterSell, Beam OutSell, Better Price, BiteSpeed, Bogos, Bold Brain, Bold Bundles, Bold Custom Pricing, Bold Motivator, Bold Product Options, Bold Subscriptions, Bold Upsell, BookThatApp, Booster Page Speed Optimizer, Boutiq, CareCart Sales Pop Up, Carro, Cartylabs, CJDropshipping app, Coin Currency Converter, Conjured, Conversio App, Cozy AntiTheft, DelightChat, Delm, Digismoothie Candy Rack, Drop A Hint, Easy Hide PayPal, Easy Redirects, EasyGift, Enlistly, EraofEcom Cartroids, EraofEcom MTL, EraofEcom WinAds, Fast Bundle, Fera Product Reviews App, FireApps Ali Reviews, Flits, Fontify, Frequently Bought Together, Froonze, GemPages, Gist Giftship, Globo Also Bought, Globo Color Swatch, Globo Form Builder, Globo Pre-Order, Govalo, GTranslate app, Helixo UFE, Hextom Free Shipping Bar, Hextom Ultimate Sales Boost, HulkApps Age Verification, In Cart Upsell & Cross-Sell, Instafeed, Jilt App, Juphy, Justuno App, Kilatech, Klip, LangShop, LayoutHub, Leaflet platform, Littledata, Livescale, Locksmith, MinMaxify, Obsidian Incentivize, Obviyo, Omnisend Email Marketing & SMS, Order Deadline, OrderLogic app, Ordersify Product Alerts, Packlink PRO, Paloma, PerfectApps Swift, PickyStory, Picture It, PreProduct, Privy App, Product Personalizer, PushDaddy Whatsapp Chat, Qikify, Quoli, Rapid Search, Recomify, ReConvert, Releasit COD Form & Upsells, Reserve In-Store, Retention.com, Return Prime, Revy, SchemaPlus, Seal Subscriptions, Secomapp, ShipTection, Shogun Landing Page Builder, Shopapps, Shopify Buy Button, Shopify Geolocation App, ShopKeeper Tools, ShopPad Infinite Options, Shortly, Simplio Upsells, Skio, Smile App, Spin-a-Sale, SuperLemon app, Sweet Upsell, Swym Wishlist Plus, Tabarnapp, Tada, Tern, TikShop, Timesact, Track123, Trackify X, Tyslo EasySell, Video Greet, Visely, Visual Quiz Builder, Vitals, WideBundle, Wishlist King, YMQ Product Options Variant Option, Yotpo Subscriptions, YouPay, Zakeke Visual Customizer, Zalify, ZendApps, Zipify OCU, Zipify Pages

**Shopify themes** (3): Belliza, Conversion Bear, Shoptimized

**Payment processors** (166): Adyen, Affirm, Afterpay, Amazon Pay, American Express, Amex Express Checkout, Aplazame, Apple Pay, Apxium, authorize.net, Auxilia, Barion, Binance Pay, Bitcoin, BitPay, Bolt Payments, Bontii, Bootpay, Braintree, Bread, BridgerPay, Briqpay, bSecure, Catch, ChargeAfter, Chargebee, Chatt, Checkout.com, CitrusPay, Coinbase Commerce, Conekta, Convertim, Culqi, Cybersource, DEUNA, DivideBuy, Divido, doxo, Dwolla, eWAY Payments, Facebook Pay, Fat Zebra, Feroot, FinConnect, Flip-Pay, Forte, Four, Google Pay, Google Wallet, Grab Pay Later, Heartland Payment Systems, HiPay, Iamport, Instamojo, iugu, iyzico, jQuery Payment, Juspay, JUST, Klarna Checkout, Klasha, Knit pay, KueskiPay, Laterpay, LawPay, LayUp, Lemon Squeezy, Liberapay, Mastercard, Midtrans, MiniBC, Mintpay, mobicred, Mokka, Mollie, Moneris, Mul-Pay, Omise, OpenPay, Ordergroove, Pace, Paddle, Pagar.me, PagSeguro, Paidy, Partial.ly, Pay., PayBright, Paycove, Paydock, PayFast, Payflex, PayGreen, PayHere, Payl8r, Paymattic, Paymentus, Payoneer, PayPal, Payplug, Payrexx, Paysafe, Paysera, PAYTR, PayU Payment, PayWhirl, PCI Proxy, Pelcro, Pesapal, Pin Payments, Plaid, Plenigo, POLi Payment, Prive, ProcessOut, Prommt, Razorpay, Recharge, Recurly, RevCent, Scalapay, SendOwl, Service Provider Pro, Sezzle, Shop Pay, Shopflo, Shoppable, Simpl, SkyVerge, Sogecommerce, SplitIt, Spotii, SpotOn, SpurIT Partial Payments App, SpurIT Recurring Payments App, Square, Stax, Stripe, SumUp, T1 Pagos, Tabby, Tamago, Tamara, Tap Payments, TNS Payments, Venmo, Verifone 2Checkout, Visa, Visa Checkout, Voltage, Wallkit, WayForPay, WEBXPAY, Wepay, Wirecard, WorldPay, Wyre, Xpresslane, Xsolla, Yampi Checkout, Yever, YooMoney, YouCan Pay, Yuno, Zip, Zuora

**Buy now pay later** (33): Addi, Atome, cashew, Deko, etika, Fundiin, HeyLight, hoolah, Humm, LatitudePay, LayBuy, Limepay, Octane, Oney, Pagolight, Pay It Later, PayJustNow, PayPal Credit, Payva, Postpay, PowerPay, Prospa, ResolvePay, SeQura, Shop Pay Installments, Soisy, SplittyPay, Stage Try, TryNow, ViaBill, Wizpay, ZestMoney, ZoodPay

**Returns** (15): AfterShip Returns Center, EyeFitU, Happy Returns, Loop Returns, Narvar, ParcelPanel, Refundid, Reshop, Returnflows, ReturnGO, Returnly, Seel, Seko OmniReturns, ShippyPro, Sorted Return

**Shipping carriers** (68): 4Partners, APC, Asendia, Australia Post, B2C Europe, Billbee, Bleckmann, Boxtal, Bpost, BRT, Budbee, Celeritas, Chronofresh, Chronopost, CityMail, Colis Privé, Colissimo, Correos, Corso, Coureon, CTT, Cubyn, Dachser, Delivengo, Deutsche Post, DHL, DPD, DX, Easylog, Ecovium, Envialia, FedEx, France Express, Frequenceo, GEODIS, GLS, Hermes, Homerr, Keen Delivery, LogoiX, Mondial Relay, MRW, My Flying Box, NACEX, Nexive, Osterreichische Post, Parcelforce, Pickrr, Poste Italiane, PostNL, Red je Pakketje, Relais Colis, Royal Mail, SEUR, Sherpa, ShipStation, Shipup, T1 Envios, Tipsa, Transmart, Trunkrs, UK Mail, UPS, USPS, Waaship, Whistl, Yodel, Zeleris

**Fulfilment** (12): AfterShip, Bobgo, Deliverr, Descartes, Enviopack, Extend, Malomo, MapMyChannel, Planzer, Route, Shoprunner, VeraCore

**Reservations & delivery** (96): Aspio, BedBooking, Bobonus, BokaBord, Bookatable, BookDinners, Booking Experts, Booking Factory, Bookteq, Bottle, Clock PMS, Clorder, CoverManager, Cubilis, DISH, Easy Rez, Eatself, EatStreet, Elina PMS, Eviivo, Findigs, Firefly Reservations, Fleksa, Flipdish, Flybook, FoodBooking, Foodomaa, Foratable, Formitable, Funbutler Booking, Gastronaut, GlobRes, GloriaFood, GoPrep, Growcer, Guestonline, Guesty, HomHero, Hostmeapp, KoobCamp, Kross Booking, Little Hotelier, LobbyPMS, Lodgify, Loopi, Lumit, Maxxton, Menufy Online Ordering, Menuu, Moder, MyRest, Namastay, Octorate, Oddle, OpenTable, Ordering, Overfull, ParkFlow, Planyo, Quandoo, Reconline, ResDiary, Resengo, Reservio, Resmio, Resy, Revinate, Roompot, Simplotel, Skiperformance, Slice, Straiv, TableBooker, TableCheck, TableFever, Tableo, Tashi, Thefork, TourCMS, Travello, Tripleseat, Triptease, Typo 00, Uplisting, Upserve, Ureserv, Vacation Labs, VisBook, WeeBnB, WINEAROUND, Witbooking, WuBook, Yelp Reservations, Zenchef, Zonal Bookings, Zuppler

**Ticket booking** (53): Adalte, Agoda, Airdata, Asksuite, Beyonk, Bileto, Book N Pay, Busify, ClickBus, Cooltix, Dice, Droplabs, Etix, EzTix, Fatsoma, Fever, Full On Sport, Gevme, Guidap, Haku, HelixPay, HoldMyTicket, Indexic, InEvent, Invitario, KKTIX, Luma, Musement, OpTuNE, Planne, Planning Pod, PromoTix, Race Roster, Radario, Seated, ShowClix, Singenuity, SquadUP, Starboard Suite, Stay22, Tickera, Ticketbro, Ticketmeo, TicketSpice, Ticketure, Timepad, Tito, Tix, TuriTop, Ventrata, vFairs, Weezevent, WeTravel

**Cross border ecommerce** (11): Borderfree, ESW, Exemptify, Flow, Global-e, GlobalShopex, Glopal, Localised, With Reach, WorldShopping, Zonos

</details>

<details>
<summary><b>Content & Web Platforms</b> — 1,387 vendors</summary>

**CMS** (493): 1C-Bitrix, 321 CMS, 6Valley eCommerce CMS, a-blog cms, AbhiCMS, AboutMyClinic, AdminBuy, Adobe Experience Manager, Adobe Experience Manager Edge Delivery Services, Adobe Experience Manager Franklin, Agility CMS, Aksara CMS, Alinea, Altis, AlvandCMS, Ametys, Amiro.CMS, Amplience, Antee IPO, ApostropheCMS, AquilaCMS, Arc XP, Arya CMS, AsciiDoc, Autoconf, AutoManager, Azko CMS, Azuriom, Backdrop, Bahooosh, Banno Banking, Banshee, Base44, Batflat, Bentobox, BIGACE, BigTree CMS, Bloomreach, Bludit, BoidCMS, BoldGrid, Bolt CMS, BookingKoala, BOOM, Botble CMS, Brightspot, Brizy Cloud, Brownie, BrowserCMS, Builder.io, Business Catalyst, Business Website Builder, ButterCMS, Caisy, Caramella, Carbonmade, caSaaS, Cendyn, Chameleon system, Chayns, Chorus, Citizen Space, CivicPlus, Ckan, ClientXCMS, Clinic Sites, Clonando, CloudCannon, Cloudrexx, CMS Caddy, CMS Made Simple, CMSimple, Coaster CMS, Concrete CMS, Congressus, Contao, Contenido, Contensis, ContentBox, Contentful, Contento, Contentstack, Corebine, CoreMedia, CoreMedia Content Cloud, Cornerstone, Cosmic, Cotonti, CPG Dragonfly, CppCMS, Craft CMS, Cratejoy, Crexi, Croct, Croogo, CrownPeak, CUE, Danneo CMS, DataLife Engine, DatoCMS, Daxko, Decap CMS, DedeCMS, Delta Media, Demio, DeskPro, DESTOON, Directus, Disciple, Django CMS, DM Polopoly, DNN, Dr. Leonardo, Drupal, Duda, Duopana, Dynamicweb, E-monsite, e107, Ebasnet, eClass, eDirectory, Edlio, Ektron CMS, Elcom, Eleanor CMS, Elexio, Elgg, Emergent, Enagic, enduro.js, EngagementHQ, Enjin CMS, Enjore, Enonic, ERPNext, Essent SiteBuilder Pro, eSyndiCat, Evolve Media, experiencedCMS, ExpressionEngine, EyouCMS, eZ Publish, FaraPy, Finalsite, Flazio, FlexCMP, Flexmls, FlipBuilder, Fork CMS, Format, Gannett CMS, Geonetric, GetSimple CMS, getUBetter, Ghost, Gnuboard, GoDaddy Website Builder, Google My Business, Google Sites, govCMS, Graffiti CMS, GraphCMS, Grav, Green Valley CMS, Griddo, GX WebManager, Halo, Hatena Blog, HCL Digital Experience, Hinza Advanced CMS, Hocalwire, Holduix CMS, Hosttech Website Creator, Hotaru CMS, Hubb, Huberway, HubSpot CMS Hub, HumHub, i-motor, Ibexa DXP, Icordis CMS, iEXExchanger, immediaCMS, imperia CMS, ImpressCMS, ImpressPages, Inblog, Indexhibit, Indico, Influx CMS, Infront, InstantCMS, InterRed, Invision Community, ISAY, iScripts, It'seeze, iTCHYROBOT, iWiki, Jadu, Jadu Central Content, Jahia DX, Jalios, JamFeed, Jimdo, Joomla, JouwWeb, Justia, K-Sup, Kentico CMS, Kirby, KIT CMS, Kleeja, Kleer, Koala Framework, Koken, Kommand, Komodo CMS, Kontent.ai, Koobi, Kooboo CMS, Kotisivukone, Kreatio, Labrador CMS, Lede, LEPTON, LGC, Liana, Lieferando, Liferay, LightMon Engine, Lithium, Live Story, LiveStreet CMS, LocalGov Drupal, LocomotiveCMS, Lodel, MAAK, MacroActive, Maglr, Magnolia CMS, Maisey, Mambo, Marketpath CMS, MaxenceDEVCMS, MaxiCMS, MaxSite CMS, Megagroup CMS.S3, Melis Platform, MemberStack, Methode, MGPanel, microCMS, Microsoft SharePoint, Microweber, Milestone CMS, miniCal, Miniflat, Mirvac, MODX, Moguta.CMS, MotoCMS, Movable Type, Mozard Suite, Mura CMS, MyDryCleaner, Mynetcap, NamelessMC, NationBuilder, Naviga, Neos CMS, Nepso, Nethouse Website Builder, Newt, NexusPHP, Norse Env, NorthStar Civic, NovaDB, Nrdevo, Nucleus CMS, Nukeviet CMS, October CMS, Odoo, Ohava, Omeka, Omni CMS, Omurga Sistemi, onpublix, Open edX, OpenCities, OpenCms, OpenElement, OpenNemas, OpenText Web, OpenText Web Solutions, Optimizely Content Management, Oracle Content Management, Orchard Core, Pagefai CMS, Pagekit, Pagetiger, PagineGialle, papaya CMS, Pars Elecom Portal, PatientSites, Payload CMS, Paymenter, Pegboard7, PencilBlue, Percussion, Phoenix Site, PhotoShelter, PHP-Nuke, PHPBoost, phpCMS, PHPFusion, phpRS, phpSQLiteCMS, phpwcms, phpwind, Pimcore, Pingoteam, pirobase CMS, Pixieset Website, Pixnet, PizzaNetz, Plate, PlatformOS, Pligg, Plone, Popmenu, Portal, Posterous, Prater Raines, Prepr, Prismic, Privia Health, ProcessWire, Procurios, Progress Sitefinity, ProSites, Proximis Unified Commerce, Public CMS, Publishrr, PubLive, Publive, Pulse CMS, PyroCMS, QoreAI, Quant, Quick.CMS, Quintype, Rally, Rayo, RBS Change, RCMS, React Bricks, Reactive, RebelMouse, REC, REDAXO, RhinoFit, Rhymix, RiteCMS, Roadiz CMS, RockRMS, Rofofk, Roya, rSchoolToday, Rubedo, S-COREpion, Saffire, Sanity, Sanity.io, Sapren, Sarka-SPIP, Scorpion, Scrivito, SDL Tridion, SeamlessCMS, SeoToaster CMS, Serendipity, Shift4Shop, Shopistry, ShoutCMS, Shuttle, SIDEARM Sports, Silverstripe, simploCMS, Simplébo, SIMsite, Sitecore, Sitecore Experience Platform, SiteEdit, Siteglide, SiteManager, Sitepark IES, Sitepark InfoSite, Sitevision CMS, SiteWrench, Sivuviidakko, SixCMS, Skeeks, Skilldo, Skolengo, Skool, Smallbox, SMART L-Gov, SmartSite, Smartstore Page Builder, sNews, Social Pinpoint, SolidPixels, Solodev, Sotel, Spark CMS, SPIP, SpiralCMS, Squarespace, Squiz Matrix, Statamic, Stellantis, Storyblok, Strapi, Strato Website, Streamroll, Strife, Strikingly, Subrion, SugarWOD, Sulu, Suncel, Telescope, Tendenci, Terminalfour, Textpattern CMS, Thelia, Thrillshare, TiddlyWiki, Tiki Wiki CMS Groupware, Tilda, Tistory, TN Express Web, Tokeet, Tooning, TownNews, Twilight CMS, TYPO3 CMS, Umbraco, UMI.CMS, UNA CMS, Unicorn Platform, Uniform Digital Experience, Unstack, Ushahidi, Varbase, VerseOne, Vigbo, Vignette, VIVVO, Voog.com Website Builder, Vox Media, Vvveb CMS, Wagtail, Walla, Webcool CMS, webEdition, WebGUI, Webhealer, Weblication, Weblium, WebNode, Webreed, Website Creator, WebSite X5, WebsiteBaker, WebsPlanet, WebZi, Webzie, Weebly, WHMCS, Winter CMS, wisyCMS, Wix, Wolf CMS, Woltlab Community Framework, WordPress, Wuilt, Xiuno BBS, XOOPS, XpressEngine, youCMS

**Page builders** (210): Acquia Site Studio, Adalo, Adobe Portfolio, Alboom Prosite, AllMyLinks, ApexPages, Appjustable, Appy Pie Builder, Art Schema, Assemble, B12, BaseKit, Baya, Beae, Beezer, Behzi, BeyondMenu, Blutui, Boats Group, Boxmode, Breakdance, Bricks, Bricksite, Brizy, Brizy WordPress, Brushd, Bubble, Cantrip, Canva, Cargo, Carrd, CartFlows, Caspio, Chinese Menu Online, CoffeeCup, Control, Convertri, Convrrt, Craftum, Creatium, Destinet, Directorist, Divhunt, Divi, Doteasy Website Builder, DotGo, Droip, Durable, Easy Web Editor, Elementor, EverWeb, FASO, Ferret One, Finsweet, Flexbe, FlexiFunnels, Flipsite, Flipsnack, Framer Sites, Frontastic, Funnelish, Get Siimple, Goope, GrapesJS, GreatPages, GroovePages, Heroic, Heyflow, Homestead, Hostinger Horizons, Hostinger Website Builder, Hotel Propeller, Hypervisual Page Builder, Instant, Instapage, Italiaonline, Jacklist, Jottful, Kapix Studio, Kites, Kopage, Kubio Builder, Kyvio, Ladipage, Landingi, Launchrock, LeadPages, Level 5, LiveBooks, LiveEdit, LiveSite, Lovable, Mahara, MailerLite Website Builder, Makeswift, Menufy Website, Mobirise, Modulify, Mono.net, Motive, Mottor, Mysitefy, MySiteNow, MyWebsite, MyWebsite Creator, MyWebsite Now, Nebula Sites, Netlify Create, Nicepage, Notion, Onepage, OnUniverse, Oopy, Optimx Sports, Oracle Application Express, Ova, Oxygen, Pagecloud, PageFly, Pagemaker, Pagevamp, PARSICO, Partner Fleet, Peraichi, Pickaxe, Pineapple Builder, Pixelesq, Pixenio, Planoplan, Plasmic, Platforma LP, Pobo, Podpage, Popsy, PromoBuilding, QUV, RapidWeaver, Rawabit, Readymag, Real Geeks, Replo, Retrina Builder, Revize, Rocketspark, Sellful, Sharing, Shogun Page Builder, Showit, Silex, Simple.ink, Simvoly, SiteGalore, Siteklik, Siter, SiteW, SiteWright, Sitey, Siweb, Sketchanet, Snapps, Sociavore, Softr, Solo, SpotHopper, Springnest, Sqwiz, Stackbit, StackerHQ, Stardekk, Starhost, STUDIO, Super Builder, Swipe Pages, Taptop, TeleportHQ, The Church Co, Themify Builder, Tunosite, Umso, Untree, Venngage, Vev, Vintcer, Visual Composer, Vitrin.me, Voog, Weaverse, WebBoss, Webcake, Webflow, Webito, Webready, WebsiteBuilder, Webstudio, Webware, WebWave, Webydo, WeWeb, Wized, Wolters Kluwer, WordPress Block Editor, WordPress Site Editor, wpBakery, Ycode, YOAPress, Yola, Zarla, Zeta Producer, ZipWP, Zoho Sites

**WordPress plugins** (192): a3 Lazy Load, AddToAny Share Buttons, Advanced Custom Fields, Age Gate, Akismet, AMP for WordPress, Animate It, Animation Addons, Asgaros Forum, Astra Widgets, Autoptimize, Beaver Builder, Better Click To Tweet, Better Search, BetterDocs plugin, Blocksy Companion, Bold Page Builder, Breadcrumb NavXT, Brilliant Web-to-Lead, BuddyPress, Caldera Forms, Chimpmatic, CiviCRM plugins, Contact Form 7, Cookie Information plugin, Core Framework, Creativ.eMail, Crocoblock JetElements, Custom Fonts, Cwicly, Distributor, Dominate WooCommerce, Doppler for WooCommerce, Doppler Forms, Download Monitor, Draftpress HFCM, Easy Accordion, ElasticPress, Elementor Header & Footer Builder, ElementsKit, Embed Optimizer, EmbedPlus, Endurance Page Cache, Enhanced Responsive Images, Essential Addons for Elementor, Essential Blocks, Etch, EWWW Image Optimizer, ExactMetrics, Extendify, Flying Analytics, Flying Images, Flying Pages, FlyingPress, FooPlugins FooGallery, Formidable Form, Frames, Funnelforms, GenerateBlocks, GeneratePress GP Premium, Genesis blocks, GoDaddy CoBlocks, Google Tag Manager for WordPress, GPT AI Power, Gravity Forms, Greyd.Suite, GTranslate, Gutenberg, HollerBox, HubSpot WordPress plugin, Image Placeholders, Image Prioritizer, Imagely NextGEN Gallery, iThemes Security, Ivory Search, JetEngine, Jetpack, Jetpack Boost, JetTabs, Jilt plugin, Kadence WP Blocks, Kirki Customizer Framework, Leaky Paywall, Limit Login Attempts Reloaded, LiveCanvas, MailChimp for WooCommerce, MailChimp for WordPress, MailerLite plugin, Master Slider Plugin, MetaSlider, Modern Image Formats, Modula, Moneris Payment Gateway, MonsterInsights, Motion.page, Newspack, Ninja Forms, OnePress Social Locker, Optimization Detective, OptinMonster plugin, OrbitFox, Otter Blocks, Perfmatters, Performance Lab, Performant Translations, Photo Gallery, PixelYourSite, Polylang, Popup Maker, Powerfolio, Premio Chaty, Pretty Links, Price By Country, ProfilePress, PublishPress Blocks, RafflePress, RankMath SEO, Really Simple CAPTCHA, ReCaptcha v2 for Contact Form 7, Recent Posts Widget With Thumbnails, Redux Framework, Responsive Lightbox & Gallery, Rich Plugins Reviews, SeedProd Coming Soon, Shortcodes Ultimate, ShortPixel Image Optimizer, SiteGuard WP Plugin, SiteOrigin Page Builder, SiteOrigin Widgets Bundle, Slim SEO, Smart Slider 3, Smash Balloon Instagram Feed, Spectra, Speculative Loading, SpeedyCache, Spexo Addons, Stackable, SuperPWA, Supsystic, SVG Support, TablePress, The Events Calendar, ThemeIsle Menu Icons, ThimPress Course Review, ThimPress Course Wishlist, ThimPress Gradebook, ThimPress LearnPress, Thrive Apprentice, Thrive Architect, Thrive Comments, Thrive Leads, Thrive Quiz Builder, Thrive Ultimatum, Translate WordPress, TranslatePress, Ultimate Addons for Elementor, Ultimate Tables, UltimatelySocial, Visual Portfolio, Web Worker Offloading, WebFactory Maintenance, WebFactory Under Construction, WebToffee Stripe Payment Plugin for WooCommerce, WooCommerce Blocks, WooCommerce Multilingual, WooCommerce PayPal Checkout Payment Gateway, WooCommerce PayPal Payments, WooCommerce Stripe Payment Gateway, WooCommerce Subscriptions, Wordfence, Wordfence Login Security, WordPress Popular Posts, WP Automatic, WP Courseware, WP Fastest Cache, WP Featherlight, WP Google Map Embed, WP Google Map Plugin, WP Grid Builder, WP Job Openings, WP Live Visitor Counter, WP Maintenance Mode, WP Portfolio, WP-Optimize, WP-PageNavi, WPForms, WPML, WPMU DEV Smush, WPS Visitor Counter, XYZScripts, Yoast Duplicate Post, Zakeke Interactive Product Designer

**WordPress themes** (152): AFThemes CoverNews, AitThemes, AndersNoren Baskerville, AndersNoren Fukasawa, AndersNoren Hemingway, AndersNoren Hitchcock, AndersNoren Lovecraft, Apollo13Themes Rife, Astra, aThemes Airi, aThemes Astrid, aThemes Hiero, aThemes Moesia, aThemes Sydney, Auberge, BeTheme, Blocksy, Blossom Travel, Bold Themes, Candid Themes Fairy, Catch Themes Catch Box, Catch Themes Fotografie, Codetipi, Colibri WP, Colorlib Activello, Colorlib Illdy, Colorlib Shapely, Colorlib Sparkling, Colorlib Travelify, ColorMag, Cryout Creations Bravada, Cryout Creations Fluida, Cryout Creations Mantra, Cryout Creations Parabola, CSSIgniter Olsen Light, CyberChimps Responsive, Enigma, Envo eCommerce, Envo Shop, Envo Storefront, ExtendThemes Calliope, ExtendThemes EmpowerWP, ExtendThemes Highlight, ExtendThemes Materialis, ExtendThemes Mesmerize, FalguniThemes Nisarg, FameThemes OnePress, FameThemes Screenr, Futurio, GeneratePress, Genesis theme, GoDaddy Escapade, GoDaddy Go, GoDaddy Lyrical, GoDaddy Primer, GoDaddy Uptown Style, Graphene, HashThemes Total, Hello Elementor, Hestia, Kadence WP Kadence, Kadence WP Virtue, Kaira Vogue, LandingPress, Lightning, LTheme, LyraThemes Kale, MachoThemes NewsMag, MangaReader, MDBootstrap WP theme, Metro CreativeX, MysteryThemes News Portal, MysteryThemes News Portal Lite, MysteryThemes News Portal Mag, Neve, OceanWP, OnePage Express, OutTheBoxThemes Panoramic, Page Builder Framework, Phlox, PopularFX, Press Customizr, Press Hueman, PressMaximum Customify, Satori Studio Bento, Scissor Themes Writee, Semplice, Sinatra, SiteOrigin Vantage, SitePoint, SNO Flex, SpiceThemes SpicePress, The Theme Foundry Make, Theme Freesia Edge, Theme Freesia Photograph, Theme Freesia ShoppingCart, Theme Horse Attitude, Theme Horse NewsCard, Theme Vision Agama, Theme4Press Evolve, Themeansar Newsberg, Themeansar Newsup, Themebeez Cream Magazine, Themebeez Orchid Store, Themegraphy Graphy, ThemeGrill Accelerate, ThemeGrill Cenote, ThemeGrill ColorMag, ThemeGrill eStore, ThemeGrill Flash, ThemeGrill Radiate, ThemeGrill Spacious, Themes4Wp Bulk, ThemeZee Donovan, ThemeZee Poseidon, ThemeZee Wellington, ThemezHut Bam, ThemezHut HitMag, Themonic Iconic One, Think Up Themes Consulting, Think Up Themes Minamaze, Twenty Eleven, Twenty Fifteen, Twenty Fourteen, Twenty Nineteen, Twenty Seventeen, Twenty Sixteen, Twenty Ten, Twenty Thirteen, Twenty Twelve, Twenty Twenty, Twenty Twenty-Five, Twenty Twenty-Four, Twenty Twenty-One, Twenty Twenty-Three, Twenty Twenty-Two, Understrap, UpSolution Zephyr, Vertex, Waveme, Weaver Xtreme, Webriti Busiprof, WEN Themes Education Hub, WEN Themes Signify Dark, Woodmart, Woostify, WordPress Default, WP Puzzle Basic, WP-Royal Ashe, WP-Royal Bard, Xtra, Zakra

**Blogs** (23): Aegea, Bear Blog, Beehiiv, Blogger, BUROGU, Dotclear, DropInBlog, Haloscan, Hashnode, Jugem, LiveJournal, Medium, Overblog, Postach, Quickblog, Substack, Superblog, Svbtle, Tumblr, Typecho, TypePad, Virgool, Zinnia

**Wikis** (12): Apache JSPWiki, Atlassian Confluence, DokuWiki, Foswiki, ikiwiki, MediaWiki, MoinMoin, PukiWiki, TWiki, WikkaWiki, XWiki, YesWiki

**Documentation** (48): Adobe RoboHelp, Apigee, Asciidoctor, BetterDocs, BookStack, Bump, ClickHelp, ClickUp, DocFX, Docsify, Doctave, Docusaurus, Doxygen, Furo, GetTerms, GitBook, Haddock, HelpDocs, Intercom Articles, Javadoc, Manula, mdBook, MkDocs, MyPersonas, Obsidian Publish, phpDocumentor, Postman API Documentation, Raneto, RDoc, Read the Docs, ReadMe, ReDoc, Released, ReSpec, Scalar, Sourcey, Speca, Sphinx, Starlight, Stoplight, Support Hero, Swagger UI, TechTarget, TypeDoc, Wiki.js, YUI Doc, Zendesk★, Zensical

**Photo galleries** (24): Alboom Proof, Blessing Skin, Bloom Portfolio, bxSlider, Canvy, Chevereto, Clickbooq, Coppermine, Gallery, Imagekit, JAlbum, Keepeek, Lightfolio, Lychee, Master Slider, NextGEN Gallery, PhotoSwipe, phpAlbum, Piwigo, Pixpa, SmugMug, Theasys, Wfolio, Zenfolio

**Static site generator** (29): Adobe Muse, Astro, Bridgetown, Cecil, Eleventy, Gatsby, Gridsome, GuppY, Hexo, Hugo, Jekyll, Lume, Mintlify, Next.js Page Router SSG, Nextra, Octopress, Pelican, Phenomic, Publii, Quarto, Retype, Rspress, Saber, Scully, SitePad, Surge, VitePress, VuePress, Zola

**Message boards** (47): bbPress, Circle, CometD, Community, Copiny, Countable, Discourse, Discuz! X, ElkArte, Flarum, FluxBB, Forumbee, FUDforum, Higher Logic Vanilla, Invision Power Board, IPB, Jiglu, Linen, Mastodon, Mattermost, Mighty Network, Misskey, MyBB, Nabble, NodeBB, Oclocher, PeerBoard, PeerTube, Philomena, phpBB, PixelFed, Pleroma, Popvox, punBB, PushWoosh, Rasayel, Reddit, Remind, Simple Machines Forum, Tapatalk, Ultimate Bulletin Board, Vanilla, vBulletin, Web Wiz Forums, XenForo, XMB, YaBB

**LMS** (72): Absorb, AccessAlly, Accredible, Aforest LMS, aSc EduPage, Canvas LMS, Chamilo, Classeh, Clever, Coachy, Dokeos, EAD Plataforma, eChalk, Edmingle, Edwiser Bridge, Eloomi, Elopage, Enrollware, Famly, Forento, Genially, Graphy, Gurucan, Heights Platform, Huddle, Ilias, Inso, IrisLMS, KAMAR, Kiwify, Knoma, Knorish, Learnbase, LearnDash, LearnUpon, LearnWorlds, LearnyBox, LifterLMS, LightSpeed VT, Maestrus, Masteriyo, Mastery Manager, Mexty, Moodle, Noodle Factory, Opigno LMS, Oreed, Parentapps, Peachie, Podia, PowerSchool, PRONOTE, Punchpass, Ruzuku, Sakai, School Kiwi, Simplero Websites, Skilljar, Spayee, Spring Metrics, Teachable, Thinkific, Thought Industries, Totara, Tutor LMS, TutorCruncher, uPortal, VClasses, Voomly, Yo!Coach, Zenler, Ziber

**DMS** (13): Clicksign, Clinked, Data8, DSpace, Evernote, Invenio, Koha, Onehub, Open Journal Systems, Paperless Pipeline, ProductDyno, Typeflo, uKnowva

**Digital asset management** (32): Adobe Dynamic Media Classic, Aprimo, Aryeo, Blippa, Bluestone PIM, Brandfolder, Bynder, Canto, Celum, Censhare, CollectiveAccess, Corebook, Digizuite, Dropbox, Frontify, GraphicsFlow, Image Relay, iPaper, keep. archeevo, Mirador, Nextcloud, Optimole, PhotoShelter for Brands, Picturepark, Plytix, Salsify, Tanx, THRON, Transloadit, Vestico, Widen, Zmags Creator

**Editors** (22): Adobe GoLive, Amaya, BannerBoo, Blockly, Bluefish, CodeMirror, Draft.js, DreamWeaver, EditPlus, FrontPage, iWeb, Microsoft Excel, Microsoft PowerPoint, Microsoft Publisher, Microsoft Word, Powtoon, Summernote, Tiptap, tlooto, Unbounce, Web Stories for WordPress, WEBDEV

**Rich text editors** (14): Ace, CKEditor, Edit-in-Place, Editor.js, Etherpad, FreeTextBox, Froala Editor, Monaco Editor, N1ED, PSPad, Quill, TinyMCE, Trix, WysiBB

**Feed readers** (4): AnnounceKit, Beehiiv RSS feed, Blendle, Planet

</details>

<details>
<summary><b>Web Development & Frameworks</b> — 991 vendors</summary>

**JavaScript libraries** (235): @sulu/web, _hyperscript, Amaze UI, Amplify JS, AnythingSlider, AOS, Apollo★, ARM JS, autoComplete.js, Axios, Barba.js, basket.js, Boba.js, Boomerang, Bootbox.js, Bootstrap Table, bowser, C3.js, CamanJS, Cart.js, Chai, Choices, chroma.js, Classnames, Cleave.js, ClientJS, Clipboard.js, Closure Library, core-js, crypto-js, Darkmode.js, DataTables, Day.js, decimal.js, Dexie.js, DHTMLX, Dojo, Dropzone, Dynamics.js, EaselJS, Easy Pie Chart, Elliptic, Enquire.js, Ethers, FancyBox, FilePond, FingerprintJS, Flickity, Floating UI, FooTable, Formstone, Framer Motion, framework7, Fresco, fullPage.js, Gijgo, Glide.js, Glider.js, Goat Slider, Goober, Granim.js, Hammer.js, Handsontable, HeadJS, Highlight.js, Howler.js, html2canvas, HTML5 Media, Htmx, iCheck, imagesLoaded, Immutable.js, Infinite Scroll, Instafeed.js, Instant.Page, InstantClick, InstantGeo, Isotope, jQuery, jQuery BlockUI, jQuery DevBridge Autocomplete, jQuery Migrate, jQuery Modal, jQuery Popup Overlay, jQuery UI, JsObservable, jsPDF, JsRender, JsViews, JSZip, Karma, Keen-Slider, KerningJS, Laravel Echo, LazySizes, LazySizes unveilhooks plugin, Lenis, libphonenumber, Lightbox, List.js, lit-element, lit-html, lite-youtube-embed, Loadable-Components, Locomotive Scroll, Lodash, Lozad.js, Lunr.js, Magnific Popup, Mailcheck, Marked, Masonry, math.js, Matter.js, Mavo, metisMenu, Milonic, Mixitup, mobile-detect.js, MobX, MochiKit, Modernizr, Moment Timezone, Moment.js, Moofx, Morphext, Morris.js, mOxie, Muuri, Notie, NProgress, Offline.js, OpenCV, Orbit Slider, OWL Carousel, p5.js, Packery, Page.js, Pannellum, Papa Parse, Paraglide JS, parallax.js, Parsley.js, pdfmake, PeerJS, Peity, pickadate.js, Pikaday, Pinia, Plupload, Polyfill, Popmotion, Preact, Prefix-Free, prettyPhoto, ProgressBar.js, PubSubJS, punycode, Puter.js, qiankun, Quicklink, Ractive.js, Ramda, React Flow, React Native for Web, Responsive Nav, Retina.js, Screenfull.js, script.aculo.us, ScrollMagic, scrollreveal, Select2, Selectize, Shepherd, Showdown, sidr, Sigma.js, SignalR, SimplexNoise.js, Skitter, Skrollr, Slick, slideout, Slim Select, Slimbox, Slimbox 2, Snabbt, Snap.svg, SockJS, SoundManager, Spin.js, Spine.js, Splide, SpriteSpin, Stellar.js, Sugar, SugarJS, SweetAlert, SweetAlert2, Swiffy Slider, Swiper, Swup, Syncfusion, Tablesorter, Tabulator, TanStack, Tempus, Timeago, timeago, Tiny Slider, Tinycon, Tippy.js, Tipso, TogetherJS, Tremor, TurfJS, Twitter typeahead.js, Typed.js, Typer.js, Underscore.js, Uppy, Vex, Vuex, vxe-table, waitForImages, Web Font Loader, web-vitals, Wijmo, WookMark, Wurfl, Xajax, XRegExp, YUI, Zepto, Ziggy

**JavaScript frameworks** (85): Adobe Client Data Layer, Ajax.NET Professional, AlertifyJS, AlloyUI, Alpine.js, AMP, Angular, AngularJS, Aurelia, Backbone.js, Batman.js, BEM, Bool TypeScript, CanJS, Catberry.js, Chosen, Coffee Script, Datastar, ef.js, Ember.js, Emotion, Enyo, Essential JS 2, ExtJS, Fluid Framework, Frontity, GSAP, Handlebars, Hogan.js, Hydrogen, Inertia.js, InfernoJS, jComponent, JSS, Knockout.js, Koishi.js, Marionette.js, Meteor, Mithril, Mithril.js, Moon, MooTools, Mustache, Next.js, Next.js App Router, Nuxt.js, OpenUI5, Phaser, Polymer, Prototype, Quasar, React, React Redux, React Router, Redux, RedwoodJS, Replicache, RequireJS, Reveal.js, RightJS, Riot, Riot.js, Ripple, RxJS, Satūs, Sencha Touch, Socket.io, SolidJS, Stimulus, Stitches, Strapdown.js, styled-components, Svelte, toastr, Transifex, Twitter Flight, UmiJs, Unpoly, Vike, Vue.js, VueStrap, Webix, WeBlocks, WOW, Zone.js

**JavaScript graphics** (63): A-Frame, amCharts, Angular Gridster, anime.js, AntV G2, AntV G6, ApexCharts.js, Arbor.js, Babylon.js, Backstretch, Bokeh, CanvasJS, Chart.js, D3, dc.js, dimple, ECharts, Epoch, Exhibit, FlipClock.js, Flot, Flourish, FusionCharts, GoJS, Google Charts, Highcharts, Highstock, JavaScript Infovis Toolkit, jqPlot, jQuery Sparklines, JS Charts, KaTeX, KineticJS, Konva.js, LocalFocus, MathJax, Mermaid, NVD3, Paper.js, particles.js, Paths.js, PIXIjs, Plotly, Protovis, Raphael, Recharts, Rickshaw, Rive, shine.js, spin.js, Spline, Supersized, TeeChart, Theatre.js, Three.js, Timeplot, TradingView, uPlot, Variance, Visx, xCharts, Xzero JS, ZingChart

**Web frameworks** (92): ABP Framework, actionhero.js, Adobe ColdFusion, AdonisJS, Akka HTTP, Amber, AngularDart, Apache Wicket, Arwes, Aseqbase, ASP.NET Boilerplate, Blade, Blazor, Blitz.js, Bonfire, CakePHP, Chicago Boss, CodeIgniter, Dancer, Django, Express, FarCry, FastAPI, Fat-Free Framework, Flask, Frappe, Fresh, GLPI, Google Web Toolkit, Hamechio, HeliumWeb, Helix Ultimate, Hono, Includable, Ionic, Java Servlet, JavaServer Faces, JavaServer Pages, Kemal, Koa, Kohana, Ktor, Laravel, Leptos, Lift, Livewire, Luana, Macaron, Marko, MasterkinG32 Framework, Microsoft ASP.NET, Mojolicious, Mono, Neos Flow, Nette Framework, Nordcraft, Oat++, OpenSwoole, Parse Platform, Phoenix, Phoenix Framework, Phoenix LiveView, pinoox, Play, PyWebIO, Qwik, Reflex, Remix, Revel, Ruby on Rails, Sails.js, Sapper, Seosphera, Shiny, Shopify Web Components, Snap, SolidStart, Spring, Stencil, StimulusReflex, Streamlit, Symfony, The.com, ThinkPHP, total.js, TwistPHP, Vaadin, Web2py, Wt, Xeora, Yii, ZK

**UI frameworks** (91): Angular Material, Animate.css, Ant Design, Arco Design Vue, augmented-ui, Aura, Automatic.css, Base UI, Basil.css, Bootstrap, Bulma, Chakra UI, CivicTheme, Clarity, CoreUI, daisyUI, DevExtreme, Devup UI, Dorik AI, EasyUI, Element UI, Elm-ui, Flat UI, Flowbite, Flutter, Flyvi, Formalize CSS, GOV.UK Elements, GOV.UK Frontend, GOV.UK Template, GOV.UK Toolkit, Headless UI, HeroUI, Hypestyle CSS, IBM Carbon Design System, Kendo UI, Kobalte, Layui, Magic UI, Mantine, Material Design Lite, Material UI, Materialize CSS, MDBootstrap, MDUI, MetroUI, Milligram, MudBlazor, MUI, Naive UI, New UI, NextUI, Normalize.css, NSW Design System, Nuxt UI, Open-Props, Panda CSS, Pico CSS, PlusProComponents, Preline UI, PrimeNG, PrimeReact, PrimeVue, Pure CSS, Radix UI, Semantic UI, shadcn-svelte, shadcn/ui, Shapecss, Shoelace, siimple, Simple.css, Socraft-UI, Spatie Media Library Pro, Sprig plugin, Storefront UI, SvelteKit, Tachyons, Tailwind CSS, TDesign, UIKit, UnoCSS, USWDS, Vant, VKUI, Vuetify, W3.CSS, WebAwesome, XtrixUI, Yamada UI, ZURB Foundation

**Mobile frameworks** (7): Framework7, jQTouch, jQuery Mobile, jQuery-pjax, Onsen UI, starti.app, Wink

**Programming languages** (29): Adobe Flash, bun, C, CFML, Dart, Dragon, Elixir, Elm, Erlang, GeneXus, Go, GraphQL, Haskell, Imba, Java, Kotlin, KPHP, Lua, Node.js, Perl, PHP, Python, Ruby, Rust, Sass, Scala, TypeScript, WebAssembly, XSLT

**Font scripts** (19): Adobe Fonts, Bootstrap Icons, Bunny Fonts, Cufon, Emfont, Font Awesome, FontServer, Fork Awesome, Glyphicons, Google Font API, Hoefler&Co, i30con, Ionicons, Lucide, MyFonts, sIFR, Symbolset, Twitter Emoji (Twemoji), Typekit

**Widgets** (206): AccuWeather, AddShoppers, AddThis, AddToAny, AirRobe, Airtable, Algolia DocSearch, Answerbase, AnswerDash, AppuOnline, Arena, Avasize, Babylist, BandsInTown Events Widget, BDOW, Beyond, Bokun, Booking.com widget, Bookingkit, Booksy, Browser-Update.org, Buttonizer, Buy me a coffee, Buyee, Caast.tv, CallPage, Captivate.fm, Carbonfact, Chameleon Power, Chatango, Checkfront, Cloverly, CoconutSoftware, CodeSandbox, Colbass, Comeet, Community Box, Conditional Fields for Contact Form 7, ContentViews, Contextual Related Posts, Cool Tag Cloud, Cool Timeline, Countdown Timer Ultimate, Crayon Syntax Highlighter, Crobox, CTAwidget, Custom Twitter Feeds, Daily Deals, DailyKarma, Dynamic Conditions, eKomi, Elementor Addon Elements, Elfsight, Email Encoder for Wordpress, Embed Any Document, Embed PDF Viewer, Embedly, EmbedPress, EmbedSocial, Envybox, EverWondr, Eveve, EX.CO, FareHarbor, FeederNinja, FeedSpring, FileHippo, Fillout, FitVids.JS, FlexSlider, FlippingBook, Flockler, Forethought Solve, FoxPush, FullCalendar, GetButton, Getsitecontrol, GoCertify, Gravitec, Gridster, Gumstack, Headroom.js, Headway, Hello Bar, HT Mega, HurryTimer, Iframely, Infogram, Instabot, Instagram Feed for WordPress, Interact, InteractiveCalculator, Jetboost, Ko-fi, Laga Widget, Lifter Apps Pop-up Window, MagicBell, MailOptin, Mangeznotez, MapPress, Marketo Forms, Max Mega Menu, Meebo, Meeting Scheduler, Meks Simple Flickr Widget, Mesmerize Companion, Metronet Profile Picture, MICE Operations, MiloTree, MindBody, MiniOrange Login, Morningtrain, Moxie, Mulberry, MyBlogLog, Myhkw player, Navidium Shipping Protection, Nextsale, NowButtons, Octane AI, OkMenu, Omny Studio, Ookla Speedtest Custom, Outbrain, Owids, PageLayer, Patreon, PayKickStart, Peek, Pinboard, Pinterest, Plum Popup, Po.st, Pocket, Podigee, Podium, Popupular, POWR, Priice, ProProfs Quiz Maker, ProvenExpert, Proximis, PushAd, Pushly, Q4 Cookie Monster, RateParity, ReadAloud, ReadSpeaker, Regiondo, Remixd, Replyment, Rezdy, Rezgo, Ruby Receptionists, Salesfloor, Sassy Social Share, Setmore, SevenRooms, Shareaholic, ShareThis, ShoppingGives, Sirv, SiteMinder, Slider Revolution, SnapWidget, Social9, Sorry, SoundCloud, Sporcle, Spotify Widgets, SpurIT, Squadded, StorifyMe, Strava, Streamwood, Sumo, Supademo, Taggbox, TeamBrain, Tiqets, Tockify, Topic'it, Transistor.fm, Trinity Audio, Tripadviser.Widget, TrustYou, Twitter, Ubiliz, Ucalc, Unity, uSocial, VerifyPass, VideoPal, Volley, Waitlist, Waveform, Web Stories, Webestools, Wheelio, Whooshkaa, Wisepops, WolframAlpha, Worldz, Wowee, Yandex.Messenger, Yelp Review Badge

**Maps** (36): Amap, Apple MapKit JS, ArcGIS API for JavaScript, Baidu Maps, CARTO Analytics, ClustrMaps Widget, Develic Omnium Maps, EagleView, Geoapify, Google Maps, Here, Leaflet, Mapbox GL JS, Mapbox.js, MapLibre GL JS, Mapline, MapLoco, Mapme, Mappedin, Mapplic, Maptalks, Maptiler, Microsoft Azure Maps, Naver Maps, Neshan, OpenLayers, OpenStreetMap, Prolo Finder, RevolverMaps, Seatics, Stockist, Storeify Store Locator, StorePoint, TerriaJS, TomTom Maps, ZeeMaps

**Video players** (47): 30namaPlayer, Aniview Video Ad Player, Artplayer.js, Asciinema, Bitmovin, Blinklink, Brightcove, Cleeng, Clipara, Cloudflare Stream, Conviva, Dailymotion, Delight XR, DPlayer, Fleeq, Flowplayer, Fluid Player, Inplayer, jPlayer, JW Player, Kaltura, Magisto, MediaElement.js, Panda Video, Plyr, Presto Player, Remotion, Ruffle, Rumble, Shaka Player, SublimeVideo, Syncle, thera-LINK, Twitch Player, Uscreen, VideoJS, Videoly, Videoo.tv, Vidjet, Vidscrip, Vimeo, Vimeo OTT, Viqeo, Widde, Wistia, Wowza Video Player, YouTube

**Livestreaming** (19): Apizee, Bambuser, BigMarker, Confer With, Dyte, EasyWebinar, Firework, Go Instore, Hero, HeySummit, Klarna Virtual Shopping, Loom, MediaPlatform, Ocular, Plaza, Trovo, Viloud, Vonage Video API, Webinato

**Media servers** (7): Ausha, AzuraCast, BigPoint, Muvi, Odeum, Sardius Media, Uplynk

**Augmented reality** (26): <model-viewer>, Auglio, Cylindo, DeepAR, DressOn, Expivi, Fittingbox, Floori, Levar, Luna, mirrAR, Modelo, ModiFace, Ocuco FitMix, Perfect Corp, Plattar, Prime AI, SightCall, Tangiblee, Threekit, Thridify, Vectary, Virtooal, Vntana, YouCam Makeup, Zieny

**Geolocation** (19): BigDataCloud IP Geolocation, Bullseye, db-ip, Geo Targetly, Geobytes, ip-api, IP2Location.io, ipapi, ipapi.co, ipbase, ipdata, ipgeolocation, ipify, IPinfo, IPInfoDB, ipstack, MaxMind, Radar, StoreRocket

**Feature management** (10): Beamer, Blesta, Featurebase, FlagSmith, LaunchDarkly, LaunchNotes, Noticeable, Olvy, Split, Upvoty

</details>

<details>
<summary><b>Infrastructure, Hosting & CDN</b> — 431 vendors</summary>

**CDN** (65): 5centsCDN, Acquia Cloud Platform CDN, Airee, Akamai★, Alibaba Cloud CDN, Amazon CloudFront, Amazon S3, Arc, ArvanCloud, Azion, Azure CDN, BootstrapCDN, Bunny, CacheFly, CDN77, cdnjs, Cloud Guard, Cloudflare★, Cloudimage, Cloudinary, CreateJS, DERAK.CLOUD, DiamondCDN, DigiCDN, DigitalOcean Spaces, Dorsa Cloud, EdgeCast, EdgeOne, Edgio, Fastly★, Filestack, Fireblade, Gatsby Cloud Image CDN, Gcore, GoCache, Google Cloud CDN, Google Hosted Libraries, GotiPath, GuardFlame, Hostinger CDN, ImageEngine, Imgix, Incapsula, jQuery CDN, jsDelivr, KelonCloud, KeyCDN, KuronekoServer CDN, MaxCDN, Microsoft Ajax Content Delivery Network, MizbanCloud, Powa, RawGit, Section.io, Sotoon, StackPath, Statically, Sucuri, Tencent Cloud, TwicPics, Unpkg, Uploadcare, VergeCloud, Wangsu, Yandex.Cloud CDN

**Hosting** (53): 34SP.com, Acquia Cloud Site Factory, ALL-INKL, ANS, Aruba.it, Bluehost, Contabo, DomainFactory, Doteasy, DreamHost, Drupal Multisite, Elementor Cloud, FastComet, GoDaddy, GuideIT, Helhost, Help.com, Hetzner, Hostens, HostEurope, Hostgator, Hosting Ukraine, Hostinger, Hostiq, Hostpoint, Hypercloudhost, Hyperlane, idCloudHost, Infomaniak, IONOS, Luveedu Cloud, Mercurycloud, Mittwald, Motherhost, Nestify, Newspack by Automattic, Niagahoster, One.com, REG.RU, Rosti, Saba.Host, Sakura Internet, Smilii, Strato, Strattic, Tangled Network, UKFast, VentraIP, WebHostUK, WordPress Multisite, World4You, Xserver, YalinHost

**Hosting panels** (13): AlternC, BILLmanager, cPanel, Creoline, DirectAdmin, FeatherPanel, i-MSCP, Novaresa, Plesk, Pterodactyl Panel, TCAdmin, Tencent Waterproof Wall, VirtFusion

**PaaS** (51): Acquia Cloud Platform, Agora, Akamai Connected Cloud, Amazon Web Services, Appian, Azure, Bask Health, Bernet Cloud, Brimble, Chabokan, Cloudflare Workers, Cloudways, Deno Deploy, Deta, F5 Distributed Cloud Services, Fing, Fly.io, Flywheel, Gigalixir, GitHub Pages, Glitch, Heroku, Kinsta, Lagoon, Liquid Web, Mirus, Netlify, Nexcess, Ocea, OVHcloud, Pagely, Pantheon, Platform.sh, Pressable, Pxxl App, PythonAnywhere, Railway, Render, Seravo, SiteGround, ThingPark Enterprise, Tiiny Host, Vercel, Voximplant, Vultr, WordPress VIP, WordPress.com, WP Engine, wp.cloud, Yandex.Cloud, Zeabur

**IaaS** (7): Alibaba Cloud Object Storage Service, Amazon ECS, Clientacquisition, Dweet, Google Cloud, Leaseweb, Parmin Cloud

**Web servers** (82): Amazon EC2, Angie, AOLserver, Apache APISIX, Apache HTTP Server, Apache Tomcat, Apache Traffic Server, Artifactory Web Server, CactiveCloud, Caddy, Centminmod, Cherokee, CherryPy, CouchDB, Cowboy, Daphne, Deno, ELOG HTTP, EmbedThis Appweb, EZproxy, Ferron, GlassFish, GoAhead, Google App Engine, Google Web Server, gunicorn, H2O, HCL Domino, HHVM, Hiawatha, HP Compact Server, HP iLO, Hypercorn, IBM HTTP Server, IIS, Indy, Intel Active Management Technology, JBoss Application Server, JBoss Web, Jetty, Kangle, Kestrel, libwww-perl-daemon, lighttpd, LiteSpeed, LlamaLink Cloud Server, Microsoft HTTPAPI, mini_httpd, MiniServ, MochiWeb, Mongrel, Monkey HTTP Server, Next.js Page Router SSR, nghttpx - HTTP/2 proxy, Nginx, OpenBSD httpd, OpenGSE, OpenResty, Oracle Application Server, Oracle HTTP Server, Oracle WebLogic Server, Phusion Passenger, Resin, RoadRunner, RX Web Server, SimpleHTTP, Starlet, Tengine, thttpd, TornadoServer, TwistedWeb, Uvicorn, Warp, Weblogic Server, WEBrick, WebSphere, Winstone Servlet Container, XAMPP, Xitami, Yaws, Zend, Zope

**Web server extensions** (13): Engintron, mod_auth_pam, mod_dav, mod_fastcgi, mod_jk, mod_perl, mod_python, mod_rack, mod_rails, mod_ssl, mod_wsgi, OpenSSL, Shelf

**Reverse proxies** (8): Envoy, F5 BigIP, Hydra-Shield, IBM DataPower, Kong, MATORI.NET, Urllo, V2Board

**Load balancers** (5): Amazon ALB, Amazon ELB, Application Request Routing, Azure Front Door, Google Cloud Load Balancing

**Caching** (16): FastPixel, Google PageSpeed, LiteSpeed Cache, Litespeed Cache, NitroPack, Oracle Web Cache, RabbitLoader, RackCache, Redis Object Cache, Sitecore Experience Edge, Varnish, W3 Total Cache, WordPress Super Cache, WP Rocket, wpCache, WPCacheOn

**Performance** (37): AiSpeed, BerqWP, Blitz, Cloudflare Rocket Loader, Cloudflare Zaraz, Cronitor, Edgemesh, Fasterize, Google Cloud Trace, Gumlet, Hyperspeed, Intersection Observer, Jumbo, Loadify, Naver RUA, Nostra, OneAPM, Partytown, Piio, Priority Hints, Quadran, Queue-it, QUIC.cloud, Quicksprout, Quicq, Render Better, Request Metrics, Sections.design Shopify App Optimization, Speed Kit, Speedimize, SpeedOf.Me, SpeedSize, StatusCake, Superspeed, Turbo, Turbolinks, Website Speedy

**Containers** (4): Docker, Harbor, Proxmox VE, PubNub

**CI** (4): Code Climate, GitLab CI/CD, Jenkins, TeamCity

**Network storage** (4): Amazon EFS, IPFS, Red Hat Gluster, Synology DiskStation

**Network devices** (2): Paessler, TeamViewer

**Control systems** (3): MapTrack, Milvus, Sedna System

**Operating systems** (20): AlmaLinux, Alpine Linux, CentOS, Darwin, Debian, Fedora, FreeBSD, Gentoo, Hirschmann HiOS, Raspbian, Red Hat, Scientific Linux, SunOS, SUSE, Ubuntu, UniFi OS, UNIX, Windows CE, Windows Server, YunoHost

**Databases** (17): Amazon Aurora, Claris FileMaker, Cloudera, Dimensions AI, Firebase, Lucene, MariaDB, MongoDB, MySQL, Percona, PostgreSQL, PouchDB, Qiyeku, Redis, Solr, SQLite, Virtuoso

**Database managers** (7): 8base, Adminer, Knack, phpMyAdmin, phpPgAdmin, SQL Buddy, Xano

**Remote access** (12): Atera, Cardina, CargoServer, Chaser, Citrix, Glance, Impero, Netop, Palo Alto Networks - GlobalProtect, Pulse Secure, ShellInABox, Upscope

**Domain parking** (4): Arsys Domain Parking, GoDaddy Domain Parking, JS.org, Verisign

**Data infrastructure** (4): Databricks★, Fivetran★, Hightouch★, Snowflake★

</details>

<details>
<summary><b>Security, Privacy & Identity</b> — 231 vendors</summary>

**Security** (101): Accertify, adCAPTCHA, Akamai Bot Manager, Akamai Web Application Protector, Alibaba Cloud Verification Code, Altcha, AntiBot.Cloud, Anubis, Apruvd, ARCaptcha, Arkose Labs, AWS WAF Captcha, Basic, Blankshield, Blue Triangle, Bugcrowd, BuySafe, c/side, Captch Me, CleanTalk, Clear, ClickCease, ClickReport, Cloudflare Bot Management, Cloudflare Turnstile, CoinHive Captcha, Combahton FlowShield, ComplyAuto, Confiant, Covery, DataDome, DataGrail, Dataships, DDoS-Guard, Detectify, Digest, Drata, DutchIS, FOCUS WebWall, Forter, Fortinet FortiGate, Fraud Blocker, FraudLabs Pro, Friendly Captcha, FUGU, FunCaptcha, GeeTest, Hanko, hCaptcha, HSTS, Human Presence, Imperva, Imunify360, Jumio, Kasada, Kerberos, Keybase, Kiprotect, Konduto, Mollom, MTCaptcha, Negate, NexusPIPE, NoFraud, Norton Shopping Guarantee, NTLM, Onfido, PerimeterX, Picatcha, Preeco, Proxmox Mail Gateway, RapidSec, Really Simple SSL & Security, reCAPTCHA, Regula, SafeBase, Sardine, SecureMetrics, Securiti, Seon, SiteLock, Skyflow, Slider Captcha, SnapHost, Solve Media, SPNEGO, Sqreen, StarTest, Testflow, ThreatMetrix, Token of Trust, Trezor, TruValidate, v4Guard Checkpoint, Vanta, VAPTCHA, Variti, VentryShield, Very Good Security, WAR.PE, Yandex SmartCaptcha

**Cookie compliance** (77): 2B Advice, Acconsento.click, AdFixus, AdOpt, AdRoll CMP System, Alfright, Axeptio, biskoui, Borlabs Cookie, Byscuit, c15t, CIVIC, Clarip, clickio, Clickskeks, Clym, Commanders Act TrustCommander, Consent Manager, Conversant Consent Tool, Cookie Control, Cookie Information, Cookie Notice, Cookie Script, Cookie Seal, CookieBAR, Cookiebot, CookieFirst, CookieHub, CookieYes, CrownPeak Universal Consent Platform, Cybot, Didomi, Efilli, Enzuzo, eucookie.eu, Evidon, Funding Choices, GDPR Cookie Consent Plugin by Webtoffee, HubSpot Cookie Policy Banner, HulkApps GDPR/CCPA Compliance Manager, iubenda, Ketch, Klaro, Legal Monster, LiveRamp PCM, Metomic, Moove GDPR Consent, My Agile Privacy, Normi, OneTrust, Osano, Pandectes, Pandectes GDPR Compliance, PieEye, Privado, Privasee, PubTech, Quantcast Choice, Seers, Segment Consent Manager, Shopify Consent Management, snigel AdConsent, Sourcepoint, Spatie Laravel Cookie Consent, Tealium Consent Management, Termly, Tramoce, Transcend, TRUENDO, TrustArc, Ultimate GDPR & CCPA, Uniconsent, Usercentrics, Vera, VeraSafe, Visible Privacy, Yett

**Authentication** (38): Alliance Auth, Amazon Cognito, Apereo CAS, Apple Sign-in, Applied CSR24, Auth0, Auth0 Lock, authorized.by, Authy, Azure AD B2C, Clerk, Facebook Login, GetSocial, Google Sign-in, JumpCloud, LINE Login, Linkedin Sign-in, Login with Amazon, LoginRadius, MagicLabs, MetaMap, Microsoft Authentication, NextAuth.js, Okta, OneAll, Oxi Social Login, Passage, Passport.js, RingCaptcha, SAP Customer Data Cloud Sign-in, SimpleSAMLphp, Socure, Super Socializer, Twilio Authy, uLogin, Userbase, Vouched, WWPass

**SSL/TLS certificate authorities** (7): AWS Certificate Manager, DigiCert, Entrust, Identrust, Let's Encrypt, Sectigo, Thawte

**Cryptominers** (8): Coinhave, CoinHive, Coinimp, Crypto-Loot, deepMiner, JSEcoin, Minero.cc, Minerstat

</details>

<details>
<summary><b>Business Operations</b> — 281 vendors</summary>

**Accounting** (9): Akaunting, Carta, Epicor, Ignition, Iress, Lendi, Liscio, Taxdome, Tiller

**Recruitment & staffing** (69): 7Shifts, Agorize, Appcast, ApplicantStack, Avature, BambooHR, Beamery, BITE, Breezy HR, CATS, Converzee, Dover, DreamApply, Employment Hero, Eploy, Firefish Software, Flip, Freshteam, Getro, Greenhouse, HigherMe HR, Hireology, Homerun, HrFlow.ai, iCIMS, Indeed, JazzHR, JBoard, Job Board Fire, JobAdder, Jobiqo, Jobvite, Jobylon, Lever, Matchlab, Membership Toolkit, Mercer, Moka HR, Naukri, Nexxt, onlyfy Application Manager, OTYS, PageUp, Paradox, Paylocity, PCRecruiter, Personio, Phenom, POINT, Radancy, Recooty Job Widget, Recop, Recruitee, Recruition, Refari, Signals, SmartRecruiters, SnapHop, Staffbase, Survale, Talent Clue, TalentBrew, Talention, Teamtailor, Vincere, Webscribble, Workable, Zoho Recruit, Zwayam

**Issue trackers** (68): Asana, Atlassian Jira, Atlassian Jira Issue Collector, Atlassian Statuspage, Better Stack, BugHerd, Buglog, Bugzilla, Cachet, Canny, Checkly, Combodo iTop, cState, Faveo, Feedback Fish, Flyspray, Get Satisfaction, GetFeedback, GitLab, GlitchTip, Help Scout, HetrixTools, Honeybadger, Hund.io, Incident.io, Instatus, LoopedIn, MantisBT, Marker, Mojo Helpdesk, Mopinion, Muscula, NodePing, Noibu, Nolt, Nootiz, Oh Dear, osTicket, otrs, Phabricator, Pingdom Uptime Monitoring, Planio, RapidSpike, Redmine, Rollbar, Ruttl, Sentry, Sleekplan, SOPlanning, Stackify, Statping, Status.io, StatusCast, Statuspal, Staytus, Taiga, TeamLinkt, Trac, Upptime, UptimeRobot, UserReport, UserRules, Usersnap, UserVoice, Vigil, Ybug, YouTrack, Zammad

**Development** (75): Acquia Cloud IDE, Anima, API Spreadsheets, Apiary, Appifiny, Appwrite, Artifactory, AskHandle, Atlassian Bitbucket, Atlassian FishEye, Betty Blocks, Canyon, CheerPJ, Clarifai, ClickOnce, Clockwork, Conduit, Construct 3, Developing Azerbaijan, Dimml, EasyEngine, Famous.ai, Feednami, Filamentphp, Fixer, Forgejo, FormWise, Gamma, genezio, Gerrit, git, Gitea, Gitiles, gitlist, gitweb, Gogs, Grain Harvest, Hexia, Infinity, Intervo, Kubernetes Dashboard, Kuroco, Loop Web, MarsX, Mendix, MichiJS, Microsoft Visual Studio, MindStudio, MsCode.pl, Opal, OutSystems, Overwolf, PHPDebugBar, Prisme, Rcode Vision, Replit, Retool, RobixCM DV Team, Rual, RunKit, ScapBot, Sheety, SlickStack, SonarQube, SonarQubes, Spicy Rocket, Stammer.ai, Storybook, Subversion, Supabase, Thinkstack, Tryzens, Turbopack, WordPress Project Manager, YourGPT

**Search engines** (60): Addsearch, Algolia, Apisearch, Athena Search, Athos Commerce, Attraqt, Awesomplete, Baidu Search Box, Bloomreach Discovery, Boost Commerce, Cludo, Constructor.io, Convermax, Coveo, Dalue, Doofinder, Elasticsearch, ElasticSuite, ExpertRec, Fact Finder, FAST ESP, FAST Search for SharePoint, FiboSearch, Findbar, Findberry, Findify, Goodsearch, GroupBy, HawkSearch, Kapa.ai, Kibana, Klevu, Layers, Loop54, MageWorx Search Autocomplete, Mars Flag, Meilisearch, Miso, Nova Busca, Orama, Pickzen, Queryly, Search Magic, Searchanise, Searchine, SearchiQ, Searchspring, Searchtap, Segmentify, SEO Manager, Site Search 360, SniperFast, Swiftype, Trivago, Typesense, VuFind, WizSoft, Wizzy, Yext, Zevi

</details>

<details>
<summary><b>Miscellaneous</b> — 117 vendors</summary>

**Miscellaneous** (117): Acquia Content Hub, Acquire Cobrowse, Admiral, Azure Edge Network, Babel, Buildertrend, Buy with Prime, cgit, CoConstruct, Cocos2d, CopyPoison, DocuSign, Douban, ELOG, eNamad, EPrints, Exo Platform, Freedom Farmers, GoAnywhere, Godot, GoKwik, Google Cloud Storage, Google Code Prettify, Gravatar, h5ai, HarborByte, Hasura, Hearth, History, HTTP/2, HTTP/3, IconScout, iHomefinder IDX, Issuu, Jade, Jive, JobberBase, K2, Kakao, Klaviyo Customer Hub, Lengow, Less, Libravatar, Loqate, LottieFiles, Magewire, MemberSpace, Mentaya, Meticular, Microsoft Silverlight, Module Federation, Moon Organizer, MoverBase, NewStore, Nido Tecnologia, Nogin, nopStation, Open Graph, OpenGrok, Oracle Dynamic Monitoring Service, ownCloud, parcel, ParkingCrew, PDF.js, Permutive, petite-vue, Pixc, Popper, Porch, Prism, Product Hunt, Progress MOVEit, Progress WS_FTP, PWA, PyData Sphinx Theme, Pygments, PyScript, Recurate, ResponsiveVoice, RobixCM Generator, Rspack, RSS, Sentara, ServiceNow, Sharper MMS, SheerID, ShoppingFeeder, Slidebean, SOBI 2, SobiPro, SPDY, Splunkd, Spotify Web API, SWC, SWFObject, SyntaxHighlighter, T1 Comercios, Tapcart, Threadles, TocToc, Toky, Track Hospitality Software, TripIt, Venly, Vite, Vue2-animate, Waste Connections, Weatherstack, Webmin, Webpack, WebRTC, WebSocket, Websocket, Weekdone, WeltPixel Pearl Theme, X-Clacks-Overhead, Zabbix

</details>

## Appendix B — reference

**Match types:** `exact`, `contains`, `prefix`, `suffix`, `regex`
(case-insensitive; DNS dot-normalized).
**Strength buckets:** definitive `1.0`, strong `0.85`, moderate `0.6`, weak `0.3`.

**File layout:**
```
signatures/
  vendors.json  categories.json          # curated taxonomy
  dns/<id>.json  web/<id>.json            # curated signatures (one per vendor)
  selection.marketing_sales.json          # default GTM selection
  master/
    vendors.json  categories.json  _meta.json
    dns/all.json  web/<letter>.json       # imported Wappalyzer library (sharded)
```

**Refresh the master library:** `python -m technographics.cli import-master`
then regenerate this doc: `PYTHONPATH=src python scripts/gen_signal_catalogue.py`.
