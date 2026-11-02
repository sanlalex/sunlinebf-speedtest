# SunlineBF sur MikroTik CHR

Cette image regroupe la page SunlineBF et son historique SQLite (port TCP **8081**) avec le moteur LibreSpeed Rust (port TCP **8080**). Le moteur reçoit directement les flux de test ; la page parle au même CHR sur ces deux ports. L’historique se trouve dans `/data/results.sqlite3` et doit être placé sur un stockage RouterOS persistant.

## Compatibilité

Prévu pour **RouterOS v7 sur CHR x86_64 (linux/amd64)**. Le build compile le moteur Rust officiel au commit `9390a0226b86afe8e78177492ba1614711fddedb`. Il faut construire sur une machine Linux/amd64 avec Docker Buildx ou Podman et accès Internet. L’image et l’archive tar sont produites en local ; rien n’est installé automatiquement sur le routeur.

Depuis ce dossier (`sunlinebf/`), construire et exporter :

```sh
docker buildx build --platform linux/amd64 --load -t sunlinebf:chr .
docker save sunlinebf:chr -o ../sunlinebf-chr-amd64.tar
python export_routeros.py ../sunlinebf-chr-amd64.tar ../sunlinebf-chr-routeros.tar
```

Téléverser **`sunlinebf-chr-routeros.tar`**, produit par la dernière commande. Le script Python standard transforme l’export Docker récent (configuration dans `blobs/sha256`) en archive Docker classique (configuration à la racine et couches `layer.tar` non compressées), en vérifiant chaque couche avec les empreintes de l’image. Cela contourne l’erreur RouterOS `no config found in manifest`. Le contenu et la configuration de l’image sont conservés ; l’archive classique est plus volumineuse.

Dans Winbox, téléverser cette archive dans un stockage persistant du CHR, par exemple un disque ajouté et monté comme `disk1`. Créer aussi un dossier persistant pour `/data`, par exemple `disk1/sunlinebf-data`, puis importer l’image :

```routeros
/container/config/set tmpdir=disk1/tmp
/container/mounts/add list=mount-sunlinebf src=disk1/sunlinebf-data dst=/data
/container/add file=disk1/sunlinebf-chr-routeros.tar name=sunlinebf root-dir=disk1/sunlinebf-root interface=veth-sunlinebf mountlists=mount-sunlinebf start-on-boot=yes
```

Ces commandes supposent que les noms `disk1` et `veth-sunlinebf` existent déjà. Adapter le chemin `disk1/sunlinebf-chr-routeros.tar` au dossier où l’archive a été téléversée : `/file/print detail where name~"sunlinebf"` permet de retrouver le nom exact. Créer le montage persistant avant le conteneur.

Si une première tentative est en échec, supprimer uniquement l’entrée du conteneur échoué dans Winbox, conserver le montage et le dossier de données, puis importer la nouvelle archive. Choisir un nouveau `root-dir` vide, par exemple `disk1/sunlinebf-root-v2`, si une extraction partielle existe. Ne pas ajouter une seconde fois le montage déjà créé.

Avant le premier démarrage, vérifier `/container/print` puis lancer :

```routeros
/container/start [find where name="sunlinebf"]
```

Consulter `/container/print` et `/log/print` en cas d’erreur. La page s’ouvre à `http://<ADRESSE_ACCESSIBLE_DU_CONTENEUR>:8081/` et le moteur écoute sur `http://<ADRESSE_ACCESSIBLE_DU_CONTENEUR>:8080/`.

## Réseau du CHR

RouterOS exige un paquet `container`, l’activation locale du mode conteneur et un disque persistant. Les détails changent selon la version de RouterOS et le réseau déjà configuré. Créer/relier l’interface VETH à un bridge et ouvrir les ports 8080/8081 uniquement aux VLANs techniciens de confiance. Si les appareils n’ont pas de route vers l’adresse VETH, prévoir dans RouterOS les routes ou règles de redirection adaptées au plan IP déjà utilisé. Ne pas copier un sous-réseau d’exemple sans vérifier qu’il n’entre pas en conflit avec le réseau existant.

L’activation du mode conteneur est une action RouterOS explicite, à confirmer depuis l’accès local du CHR selon les instructions affichées par RouterOS :

```routeros
/system/device-mode/update container=yes
```

Vérifier la licence et ses limites avec :

```routeros
/system/license/print
```

## Limites à connaître

- La page et l’historique utilisent HTTP et n’ont pas de mot de passe. Garder les ports sur un réseau de gestion/techniciens fiable ; ne pas les exposer à Internet.
- Le dossier `/data` contient les résultats ; inclure `disk1/sunlinebf-data` dans les sauvegardes.
- L’historique déjà présent sur le CT 103 n’est pas migré automatiquement. Cette installation démarre avec une base SQLite vide ; prévoir une sauvegarde et un transfert cohérent si vous souhaitez reprendre les anciens tests.
- Un test à haut débit consomme le CPU et le réseau du CHR. Comme le CHR route aussi le réseau PTMP, cette charge peut ralentir le trafic et fausser les mesures. Tester en période contrôlée et surveiller le CPU ; pour mesurer le réseau sans charger le routeur, garder le moteur LibreSpeed sur le serveur Proxmox et utiliser le CHR seulement pour le routage.
- La licence gratuite de CHR limite le trafic sortant à 1 Mbit/s par interface jusqu’à l’achat d’une licence. Cela rend le CHR inadapté comme serveur de tests haut débit en licence gratuite ; utilisez plutôt le serveur Proxmox pour héberger le moteur de mesure.
- iPerf3 n’est pas inclus dans cette image ; la VM Ubuntu iperf existante reste distincte.
- L’image inclut la licence de LibreSpeed Rust (`/opt/librespeed/LICENSE.txt`) et la licence LibreSpeed de l’interface (`/opt/sunlinebf/LICENSE`).

Références RouterOS : [conteneurs](https://manual.mikrotik.com/docs/containers/), [prise en charge des architectures](https://manual.mikrotik.com/docs/getting-started/software-specifications/feature-support-based-on-architecture/).
