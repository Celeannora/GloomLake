<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# analyze this screenshot. it needs severe ui overhaul, it should look like a professional ux app. attached is the script for reference.

develop a 100 step plan/improvement guide to fix.
this will be fed to claude opus.

take guide from no less than 20 resources for ux design.

Here's the complete 100-step professional UX overhaul guide for the MTG Deck Scaffold Generator, sourced from 30 authoritative UX resources.

## What the guide covers

The 100 steps are organized into **8 actionable phases**, each targeting a distinct layer of the app:


| Phase | Steps | Focus |
| :-- | :-- | :-- |
| **1 — Design System** | 1–15 | 8pt spacing, tokens, typography scale, elevation, contrast audit |
| **2 — Layout Architecture** | 16–30 | Sidebar + content panels, step progress indicator, responsive layout |
| **3 — Mana Selector** | 31–38 | Inline 5-button row, toggle chips, color blend preview, tooltips |
| **4 — Archetype Selector** | 39–50 | Group headers, wider buttons, progressive disclosure, guild hints |
| **5 — Tribal / Tags / Options** | 51–62 | Collapsible cards, search dropdown, settings redesign, validation |
| **6 — CTA \& Feedback** | 63–72 | Multi-phase loading, toasts, undo, keyboard shortcuts |
| **7 — Query / Synergy Panels** | 73–80 | Data tables, per-query progress, log syntax highlighting |
| **8 — Polish \& Accessibility** | 81–100 | Focus rings, hover micro-lift, WCAG AA, full Nielsen audit |

## Key problems addressed from the screenshot

- **Orbital mana layout** → Replaced with a clean inline 5-button row (Step 31) per Fitts's Law[^1][^2]
- **No visual hierarchy** → Typography scale + numbered sidebar navigation (Steps 3, 17)[^3][^4]
- **Cognitive overload** → Progressive disclosure hides advanced sections (Steps 50, 56)[^5][^6]
- **Saturated mana colors bleeding into UI** → Desaturation by 15–20 points per dark mode best practices[^7][^8]
- **No system status feedback** → Multi-phase CTA, toasts, completion indicators (Steps 65, 67, 71)[^9][^10]
- **Frozen generation with no feedback** → Skeleton-style progress with cancel mechanism (Steps 65, 66)[^11][^12]
<span style="display:none">[^100][^101][^102][^103][^104][^105][^106][^107][^13][^14][^15][^16][^17][^18][^19][^20][^21][^22][^23][^24][^25][^26][^27][^28][^29][^30][^31][^32][^33][^34][^35][^36][^37][^38][^39][^40][^41][^42][^43][^44][^45][^46][^47][^48][^49][^50][^51][^52][^53][^54][^55][^56][^57][^58][^59][^60][^61][^62][^63][^64][^65][^66][^67][^68][^69][^70][^71][^72][^73][^74][^75][^76][^77][^78][^79][^80][^81][^82][^83][^84][^85][^86][^87][^88][^89][^90][^91][^92][^93][^94][^95][^96][^97][^98][^99]</span>

<div align="center">⁂</div>

[^1]: https://cieden.com/book/sub-atomic/spacing/spacing-best-practices

[^2]: https://blog.prototypr.io/the-8pt-grid-consistent-spacing-in-ui-design-with-sketch-577e4f0fd520

[^3]: https://designsystems.surf/articles/depth-with-purpose-how-elevation-adds-realism-and-hierarchy

[^4]: https://github.com/material-components/material-web/blob/main/docs/components/elevation.md

[^5]: https://www.nngroup.com/articles/visual-hierarchy-ux-definition/

[^6]: https://www.telerik.com/blogs/typographic-hierarchy-tips-creating-more-visually-appealing-readable-text

[^7]: https://www.reddit.com/r/DesignSystems/comments/1it1erb/3tier_design_token_system/

[^8]: https://www.designsystemscollective.com/the-art-of-design-tokens-a-metaphor-for-the-3-tier-token-model-e166a2ab3073

[^9]: https://www.boia.org/blog/offering-a-dark-mode-doesnt-satisfy-wcag-color-contrast-requirements

[^10]: https://testparty.ai/blog/color-contrast-requirements

[^11]: https://medium.muz.li/mastering-the-art-of-dark-ui-design-9-essential-principles-and-techniques-a673b1328111

[^12]: https://dubbot.com/dubblog/2023/dark-mode-a11y.html

[^13]: https://uxdesign.cc/dark-ui-design-principles-and-best-practices-9b9061b86e1

[^14]: https://atmos.style/blog/dark-mode-ui-best-practices

[^15]: https://millermedia7.com/blog/microinteractions-in-user-experience-design/

[^16]: https://www.nngroup.com/articles/microinteractions/

[^17]: https://blog.appmysite.com/ux-design-laws-and-principles-you-must-know-of/

[^18]: https://www.uxmatters.com/mt/archives/2024/04/15-essential-ux-design-principles-and-practices-for-developers.php

[^19]: https://learn.microsoft.com/en-us/dynamics365/guidance/develop/ui-ux-design-principles

[^20]: https://www.figma.com/resource-library/ui-design-principles/

[^21]: https://www.uxtigers.com/post/gestalt-principles

[^22]: https://www.uxtoast.com/design-tips/gestalt-principles-in-ui

[^23]: https://uxplanet.org/all-about-affordance-and-signifier-terms-by-don-norman-the-ux-pioneer-e0ea7b9b99f5

[^24]: https://uxmag.com/articles/understanding-don-normans-principles-of-interaction

[^25]: https://www.uxpin.com/studio/blog/keyboard-navigation-prototypes/

[^26]: https://www.levelaccess.com/blog/keyboard-navigation-complete-web-accessibility-guide/

[^27]: https://kitemetric.com/blogs/master-customtkinter-build-stunning-python-apps

[^28]: https://saltnbold.com/blog/post/header-vs-sidebar-a-simple-guide-to-better-navigation-design

[^29]: https://www.reddit.com/r/UXDesign/comments/1ijvs1v/desktop_dashboard_is_it_always_best_practice_to/

[^30]: https://www.designmonks.co/blog/side-drawer-ui

[^31]: https://shiftasia.com/community/applying-jakob-nielsens-10-usability-heuristics-for-better-ux-design/

[^32]: https://www.nngroup.com/articles/ten-usability-heuristics/

[^33]: https://developer.apple.com/design/human-interface-guidelines

[^34]: https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/

[^35]: https://www.justinmind.com/ux-design/progressive-disclosure

[^36]: https://uxplanet.org/everything-you-should-know-about-8-point-grid-system-in-ux-design-b69cb945b18d

[^37]: https://www.threesevenmarketing.com/blog/design-principles-cognitive-load/

[^38]: https://www.nngroup.com/articles/progressive-disclosure/

[^39]: https://ixdf.org/literature/article/fitts-s-law-the-importance-of-size-and-distance-in-ui-design

[^40]: https://blog.logrocket.com/ux-design/fitts-law-ui-examples-best-practices/

[^41]: https://www.thesigma.co/journal/fitts-law-ux-design

[^42]: https://dev.to/devasservice/customtkinter-a-complete-tutorial-4527

[^43]: https://uxplanet.org/best-ux-practices-for-designing-a-sidebar-9174ee0ecaa2

[^44]: https://www.nngroup.com/articles/fitts-law/

[^45]: https://mobisoftinfotech.com/resources/blog/microinteractions-ui-ux-design-trends-examples

[^46]: https://www.figma.com/resource-library/fitts-law/

[^47]: https://www.nngroup.com/articles/gestalt-proximity/

[^48]: https://fullclarity.co.uk/insights/gestalt-principles-in-ui/

[^49]: https://ux247.com/usability-principles/

[^50]: https://smbservices.co/blogs/microsinteractions-101-flawless-ui-design-tips/

[^51]: https://www.wix.com/studio/blog/microinteractions-ux-design

[^52]: https://anvil.servicetitan.com/docs/web/components/tooltip/design

[^53]: https://www.uxpin.com/studio/blog/what-is-a-tooltip-in-ui-ux/

[^54]: https://www.nngroup.com/articles/minimize-cognitive-load/

[^55]: https://fullclarity.co.uk/insights/cognitive-overload-in-ux-design/

[^56]: https://marvelapp.com/blog/design-principles-reducing-cognitive-load/

[^57]: https://ixdf.org/literature/topics/progressive-disclosure

[^58]: https://en.wikipedia.org/wiki/The_Design_of_Everyday_Things

[^59]: https://tianpan.co/notes/2025-08-31-the-design-of-everyday-things

[^60]: https://blog.logrocket.com/ux-design/dark-mode-ui-design-best-practices-and-examples/

[^61]: https://www.onething.design/post/skeleton-screens-vs-loading-spinners

[^62]: https://www.nngroup.com/articles/usability-heuristics-complex-applications/

[^63]: https://www.pencilandpaper.io/articles/ux-pattern-analysis-loading-feedback

[^64]: https://www.nngroup.com/videos/skeleton-screens-vs-progress-bars-vs-spinners/

[^65]: https://blog.logrocket.com/ux-design/skeleton-loading-screen-design/

[^66]: https://www.setproduct.com/blog/empty-state-ui-design

[^67]: https://www.eleken.co/blog-posts/empty-state-ux

[^68]: https://uxknowledgebase.com/affordances-signifiers-the-4th-ux-knowledge-piece-sketch-8e1191d2bc0d

[^69]: https://developer.android.com/develop/ui/compose/designsystems/material3

[^70]: https://www.useronboard.com/onboarding-ux-patterns/empty-states/

[^71]: https://www.uxpin.com/studio/blog/ux-best-practices-designing-the-overlooked-empty-states/

[^72]: https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/

[^73]: https://www.reddit.com/r/UXDesign/comments/vigsui/progressive_disclosure_in_lengthy_complex_forms/

[^74]: https://www.linkedin.com/pulse/mastering-advanced-typography-visual-hierarchy-ui-design-karimeh-txbbf

[^75]: https://www.reddit.com/r/accessibility/comments/1o0bndy/wcag2_contrast_checks_are_flawed_for_light_colors/

[^76]: https://blog.uxtweak.com/usability-heuristics/

[^77]: https://www.nngroup.com/articles/skeleton-screens/

[^78]: https://ixdf.org/literature/topics/gestalt-principles

[^79]: https://uxdesign.cc/mastering-typography-in-design-systems-with-semantic-tokens-and-responsive-scaling-6ccd598d9f21

[^80]: https://codelabs.developers.google.com/codelabs/design-material-darktheme

[^81]: https://developer.apple.com/news/?id=s9s75a8k

[^82]: https://www.xmethod.de/en/blog/diving-into-the-dark-exploring-dark-theme-ux-design-best-practices

[^83]: https://tallwave.com/blog/cognitive-load-in-ux/

[^84]: https://alvacommerce.com/ux-design-best-practices-complete-2024-guide/

[^85]: 132.jpg

[^86]: scaffold_gui-2.py

[^87]: https://www.geeksforgeeks.org/python/build-a-basic-form-gui-using-customtkinter-module-in-python/

[^88]: https://www.youtube.com/watch?v=Miydkti_QVE

[^89]: https://www.youtube.com/watch?v=Y01r643ckfI

[^90]: https://educalvolopez.com/en/blog/sistema-de-espaciado-con-grid-8pt-guia-completa

[^91]: https://designsystems.surf/articles/typography-system-101-a-step-by-step-guide

[^92]: https://www.rejuvenate.digital/news/designing-rhythm-power-8pt-grid-ui-design

[^93]: https://accessibleweb.com/color-contrast-checker/

[^94]: https://www.navbar.gallery/blog/best-side-bar-navigation-menu-design-examples

[^95]: https://northsouthtech.co/blog/ios-app-design-guidelines-for-2024/

[^96]: https://www.youtube.com/watch?v=z5oIRwZXkxI

[^97]: https://www.createwithswift.com/wwdc24-whats-new-in-the-human-interface-guidelines/

[^98]: https://designcode.io/dark-interfaces/

[^99]: https://www.youtube.com/watch?v=CByGVARMCYI

[^100]: https://www.youtube.com/watch?v=hwQvpDxgGh4

[^101]: https://fullstackdeveloper.novkovic.net/blog/vscode-figma-toolkit/

[^102]: https://blog.logrocket.com/ux-design/empty-states-ux-examples/

[^103]: https://uxguide.dotnetnuke.com/UIPatterns/Tooltips.html

[^104]: https://wise.design/foundations/focus-states

[^105]: http://inclusive-components.design/tooltips-toggletips/

[^106]: https://accessibility.asu.edu/articles/keyboard

[^107]: https://uxplanet.org/text-fields-in-ui-design-7-common-styles-ea5a76689892

