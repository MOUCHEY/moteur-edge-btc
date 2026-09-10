# Les coûts — la variable qui décide de tout

## Avertissement

Les coûts utilisés par ce dépôt sont des **hypothèses**, pas des mesures. Elles
n'ont **pas** été tirées des relevés de courtier de Jeunathan. Tant que ce n'est
pas fait, tout résultat publié ici est conditionnel à ces chiffres, et doit être
lu comme tel.

C'est la limite la plus sérieuse du dépôt à ce jour. Elle est écrite ici plutôt
qu'enterrée dans un commentaire.

## Le modèle actuel (`engine/costs.py`)

| Poste | Valeur | Origine |
|---|---|---|
| Spread | 4,0 bps | hypothèse — CFD BTCUSD retail |
| Slippage | 2,0 bps | hypothèse — exécution au marché |
| Commission | 0,0 bps | la plupart des CFD crypto n'en facturent pas |
| **Aller-retour** | **6,0 bps** | somme |
| Portage | 2,7 bps/jour | ≈ 10 %/an |

À 80 000 $ le BTC, 6 bps représentent environ **48 $ par aller-retour**.

## Pourquoi ce chiffre décide de tout

Le **slippage de mort** — l'espérance nette par trade — est la marge réelle. Une
stratégie qui gagne 8 bps par trade avec 6 bps de coûts ne gagne pas « 8 bps » :
elle gagne 8 bps *après* avoir survécu à un poste de coût qui vaut 75 % de son
gain. Si le vrai spread est de 10 bps au lieu de 4, elle est morte, et aucun
raffinement de signal ne la sauvera.

C'est pour cette raison que G1 exige `slippage_de_mort ≥ 3 × spread`, et que G3
retest à coûts × 1,5 et × 2.

## Ce qu'il faut mesurer pour remplacer ces hypothèses

Sur les relevés cTrader / IC Markets de Jeunathan, sur BTC :

1. **Spread effectif** : moyenne et 90<sup>e</sup> centile de `(ask − bid) / mid`,
   en bps, **par heure UTC**. Le spread nocturne n'a rien à voir avec celui de 15 h.
2. **Slippage réel** : `(prix d'exécution − prix demandé) / prix demandé`, signé,
   distinguant les entrées au marché des sorties sur stop. Les stops glissent plus.
3. **Commission** effective par lot.
4. **Financement overnight** réellement débité, par jour et par sens.

Puis remplacer les valeurs de `engine/costs.py` et **réexécuter toutes les
expériences déjà publiées**. Le compteur d'essais ne bouge pas — ce n'est pas une
nouvelle recherche, c'est la même avec de meilleures entrées.

## Un piège à connaître

Les données de ce dépôt viennent de **Binance spot**, alors que Jeunathan trade
sur **CFD**. Ce ne sont pas les mêmes prix, ni les mêmes heures de cotation, ni
les mêmes coûts. Un edge trouvé sur Binance spot n'est pas garanti transférable :
le CFD a son propre spread, son propre financement, et son teneur de marché peut
élargir précisément quand la stratégie voudrait entrer.

Ce risque est réel et non mesuré. Il ne se résout qu'en G7, en réel, petite somme,
en journalisant le slippage effectif contre la marge théorique.
