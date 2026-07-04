# RF Fan - Home Assistant Integration

Integration Home Assistant pour ventilateurs RF433 génériques, avec apprentissage manuel ou guidé via ESPHome.

## Objectif

Ce projet cible les ventilateurs de plafond ou muraux pilotés par télécommande RF, quand il n'existe pas d'intégration dédiée au constructeur.

L'approche retenue est volontairement générique :

1. une passerelle ESPHome sniffe les trames RF reçues ;
2. Home Assistant apprend les codes bouton par bouton ;
3. l'intégration expose une entité fan et, si besoin, une entité light.

## Fonctionnalités

- config flow Home Assistant
- mode manuel pour coller les codes RF déjà sniffés
- mode apprentissage guidé à partir des événements ESPHome
- entité fan à vitesses discrètes
- entité light optionnelle
- état supposé (`assumed_state`)
- répétition RF configurable
- synchronisation partielle quand la télécommande physique est utilisée

## Pré-requis

- Home Assistant 2026.5+
- un nœud ESPHome exposant le service `transmit_rf_fan`
- un émetteur RF433 supporté par ESPHome
- idéalement un récepteur RF433 pour le sniff et la synchro d'état

## Installation HACS

1. Ajouter ce dépôt comme dépôt personnalisé de type `Integration`
2. Installer `RF Fan`
3. Redémarrer Home Assistant
4. Ajouter l'intégration `RF Fan`

## Structure du projet

```text
custom_components/
  rf_fan/
    __init__.py
    config_flow.py
    const.py
    entity.py
    fan.py
    light.py
    manifest.json
    strings.json
    translations/
      en.json
      fr.json
esphome/
  rf_fan_example.yaml
```

## Contrat ESPHome

Le nœud ESPHome doit exposer un service Home Assistant nommé `transmit_rf_fan`.

Payload attendu :

- `action` : nom logique de l'action (`fan_speed_1`, `light_on`, etc.)
- `code` : trame RF brute sous forme de chaîne CSV (`5000,-1500,350,-750,...`)
- `repeat_count` : nombre d'émissions RF

Le nœud peut aussi publier l'événement `esphome.rf_fan_received` pour le mode apprentissage et la mise à jour d'état. Exemple fourni dans [esphome/rf_fan_example.yaml](esphome/rf_fan_example.yaml).

## Limites connues

- pas de support générique des rolling codes
- pas d'accusé de réception RF natif
- les protocoles réellement supportés dépendent de ce que la passerelle ESPHome sait sniffer et rejouer correctement
