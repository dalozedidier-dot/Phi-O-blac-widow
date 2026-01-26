# PhiO

**PhiO** est un framework de **validation contractuelle** et d’**assurance qualité épistémologique** pour **instruments scientifiques exécutables** (ex. scripts Python).
Il opère comme une couche de **tests + audit structurel + traçabilité + collecte d’évidence**, orientée **non-régression** et **reproductibilité**.

## Portée

PhiO adresse quatre blocs :

1. **Contrat technique**
   - Interface CLI (help, sous-commandes, flags)
   - Invariants de calcul (formules “golden” / propriétés)
   - Extraction statique (AST) d’éléments structurants (ex. seuils de zones)

2. **Cadres analytiques formels**
   - DD : détection de shifts de régime
   - DD-R : restauration post-choc (réelle vs illusoire)
   - Équilibre E : compatibilité structurelle sans compensation  
   *(cf. docs internes du projet, si présentes)*

3. **Baseline versionnée (non-régression)**
   - Contrat de référence sérialisé (baseline)
   - Diff explicite entre versions (breaking change documenté)

4. **Collecte d’évidence (bundle LLM / forensic)**
   - Arborescence, hashes SHA256, concaténation contrôlée, copie ciblée
   - Objectif : reproduction + débogage externe sans perte de contexte

## Non-objectifs (anti-scope)

PhiO n’est pas :
- une bibliothèque de calcul scientifique (NumPy/SciPy)
- un framework ML (TensorFlow/scikit-learn)
- un orchestrateur de workflow (Snakemake/Nextflow/Airflow)
- un outil de visualisation

PhiO **valide** des instruments ; il ne remplace pas leurs modèles.

## Prérequis

- Python 3.10+ (recommandé)
- `pytest` (tests)
- OS : Linux/macOS (Windows possible via WSL pour les scripts shell)

## Installation (mode projet)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
