# SunlineBF — test réseau terrain

Interface web pour les équipes terrain, dérivée de [LibreSpeed](https://github.com/librespeed/speedtest), avec mesure par un serveur LibreSpeed Rust et historique partagé dans SQLite.

## Démarrage

Exécuter `python server.py` dans ce répertoire, puis ouvrir `http://127.0.0.1:8081/`. Le backend LibreSpeed Rust doit fonctionner sur le même hôte au port 8080. Les variables `SUNLINEBF_HOST`, `SUNLINEBF_PORT` et `SUNLINEBF_DB` configurent l’écoute et la base. Pour un accès depuis des appareils du réseau, choisissez une adresse d’écoute adaptée au réseau de confiance.

Les résultats terminés, le technicien et le site sont conservés sur le serveur. Sauvegardez la base SQLite avec les sauvegardes du serveur. Aucun compte utilisateur n’est intégré : toutes les personnes qui peuvent accéder au service peuvent voir et ajouter des résultats ; ne pas l’exposer à Internet ou à un réseau non fiable sans contrôle d’accès. Le transport HTTP ne chiffre pas les informations.

## Vérification

`python -m unittest discover -s tests -v`

## Licence

Le moteur provient de LibreSpeed, sous licence LGPL-3.0-or-later. Voir `LICENSE` et le [dépôt d’origine](https://github.com/librespeed/speedtest).
