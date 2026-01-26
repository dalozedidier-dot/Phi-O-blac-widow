*** Utilisation
1) Ouvre ton workflow CI: .github/workflows/<ton_workflow>.yml
2) Colle le bloc du fichier collector_fix_step.yml juste avant l'étape:
   - name: Run collector max tests
     run: bash run_collector_tests.sh

*** Décision automatique
- Si le fichier n'existe pas (EXISTS? NO) -> problème de chemin/contenu repo (le test pointe un chemin absent).
- Si le fichier existe mais n'est pas exécutable -> chmod corrige et les tests peuvent continuer.
