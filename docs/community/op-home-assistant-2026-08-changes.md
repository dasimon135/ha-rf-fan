# Patch du post #1 — community.home-assistant.io/t/1017083

Le texte complet prêt à coller est dans `post-community-op-full.md`.
Ce fichier-ci liste **ce qui change et pourquoi**, pour que tu puisses relire vite.

Le post d'origine date du 12 juillet. Depuis, la v1.7.0 a changé le câblage
recommandé, le composant radio et la forme des codes. Tel quel, il fait reproduire
au lecteur exactement le bug de l'issue #16.

## Les 4 corrections qui comptent

### 1. Câblage : GDO0 partagé RX+TX → deux broches séparées

Le tableau disait `GDO0 → GPIO 4 (RF data, RX and TX)` et `GDO2 → not used`, avec un
encadré expliquant comment gérer le partage de broche. C'est précisément le montage
qui rend le récepteur sourd sur ESP32 : la broche doit changer de mode à chaque
bascule, et ça casse silencieusement la capture RMT. Ltek et Relutzzzu y ont perdu
des jours chacun.

Nouveau : `GDO0 → GPIO4` (TX seul), `GDO2 → GPIO13` (RX seul), et l'encadré explique
le symptôme au lieu de la contournement.

### 2. Composant radio : `esphome-radiolib-cc1101` → `cc1101:` intégré

Le post pointait vers le composant externe de juanboro. ESPHome a maintenant un
composant `cc1101:` natif, c'est ce qu'utilise le YAML de référence. L'ancien reste
disponible dans `rf_fan_radiolib_legacy.yaml` pour ceux déjà câblés en une broche.

### 3. Le lien vers le YAML est figé sur un vieux commit

`.../blob/7069a0d34.../esphome/rf_fan_example.yaml` — ce commit contient la version
**cassée** du lambda. Tout lecteur qui suit ce lien aujourd'hui copie le bug.
Remplacé par un lien vers `main`.

### 4. Nouvelle étape obligatoire : `rc_protocol` et `rc_code_bits`

C'est le cœur de la v1.7.0 et ça n'existait pas dans le post. Sans ces deux valeurs
lues sur la ligne `Received RCSwitch Raw:`, les codes appris sont injouables. C'est
devenu l'étape 2, avant l'installation de l'intégration.

## Les ajouts

- **La carte livrée avec l'intégration.** Le post ne parlait que de Mushroom, alors
  que `custom:rf-fan-card` est fournie et enregistrée automatiquement depuis la
  1.5.0. Mushroom passe en alternative dans un `[details]`.
- **Le suivi de la télécommande physique** : dire que c'est une égalité de chaînes
  stricte, et que tout changement du YAML de la passerelle oblige à réapprendre.
  C'est la question n°1 du fil.
- **Limitations honnêtes** : pas de code tournant / incrémental (le cas de qiang et
  Relutzzzu), et seulement les protocoles que rc_switch sait décoder (le cas de
  Ltek). Ces deux lignes auraient évité trois échanges.

## La correction de fond

L'ancienne ligne « Toggle/relative buttons […] are handled so a single tap = a
single action » n'est plus vraie depuis la v1.7.0 : le nombre de répétitions est
respecté, arrondi à l'impair. Reformulée.

## À vérifier avant de coller

Discourse mange parfois l'indentation des blocs YAML collés depuis un `.md`. Relis
le lambda de l'étape 2 et le bloc `[details]` de Mushroom.
