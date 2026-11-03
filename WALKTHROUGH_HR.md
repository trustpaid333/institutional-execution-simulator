# Vodič za projekt — hrvatski

Ovaj dokument služi da možeš **samostalno objasniti kod i logiku projekta**. Nemoj projekt predstavljati na intervjuu kao potpuno vlastoručno programiran ako nisi razumio ili pregledao pojedine dijelove.

## 1. Tržišni problem

Zamisli da fond želi kupiti **100.000 dionica** nekog likvidnog ETF-a. Ako kupi sve odjednom, može platiti veći spread i dodatni execution impact. Ako kupuje postupno, izlaže se promjeni cijene. Ako kupuje prema tržišnom volumenu, možda neće završiti nalog do kraja sesije.

Uspoređujemo tri **agresivna** načina izvršenja; ne simuliramo passive limit orders.

## 2. Što je midprice?

`mid = (best_bid + best_ask) / 2`

Ako je bid 449,98 USD, a ask 450,02 USD, mid = 450 USD i cijeli spread = 0,04 USD. Market buy u jednostavnom tržištu počinje od ask cijene, a market sell od bid cijene.

## 3. Što je basis point (bps)?

1 bps = 0,01% = 0,0001 u decimalnom zapisu.

Ako je order benchmark 45 milijuna USD, 1 bps znači oko 4.500 USD troška. Zato se execution cost često prikazuje u bps, a ne samo dolarima.

## 4. Kako rade naše strategije?

- `Immediate`: odmah kupuje/prodaje čitavu zadanu količinu. Veći `q` povećava modelirani impact penalty.
- `TWAP`: dijeli ukupan broj dionica na približno jednake integer-share dijelove kroz 20 vremenskih intervala.
- `POV`: u svakom intervalu pokušava izvršiti do 10% volumena tog intervala, ali nikada više od preostalog naloga. Može ostati neizvršeni dio.

## 5. Kako izračunavamo izvršnu cijenu?

`fill_price = mid ± (half_spread + modeled_impact)`

Za kupnju je znak `+`, za prodaju `−`. Impact raste približno kao kvadratni korijen omjera `child_order_size / depth`.

Važno: `modeled_impact` nije pravi market impact na buduće cijene; samo dodatak/odbitak u izvršnoj cijeni tog naloga.

## 6. Implementation shortfall

Za buy nalog:

`shortfall = (ukupno plaćeno za izvršeni dio - executed_shares * arrival_mid) + fees + unfilled_shares*(terminal_mid - arrival_mid)`

Za sell se predznaci cjenovnih razlika obrću. Negative shortfall je moguć kad je cijena povoljnija od početne.

Primjer (potpuno izvršena kupnja): 10.000 dionica, arrival mid 100 USD, prosječna cijena izvršenja 100,06 USD, fee 20 USD. Shortfall = 600 + 20 = 620 USD, odnosno 6,2 bps.

## 7. Zašto Monte Carlo?

Ne znamo točno kako će se cijena ili likvidnost kretati. Zato generiramo 1.000 različitih sintetičkih putanja i na svakoj testiramo iste tri strategije. Tako možemo proučiti **distribuciju** troškova, ne samo jedan rezultat.

## 8. Što nam pokazuju početni rezultati?

- Immediate ima u ovom modelu relativno stabilan trošak jer se izvršava na početku, ali trpi veći impact penalty.
- TWAP ima manji prosječni shortfall, no znatno veće oscilacije zbog kretanja cijene kroz vrijeme.
- POV ima usporediv prosjek i nešto nižu standardnu devijaciju od TWAP-a, ali u 5,2% simulacija nije završio nalog u potpunosti.

Ne smijemo zaključiti da je TWAP univerzalno najbolji: rezultat ovisi o pretpostavkama i preferencijama klijenta.

## 9. Struktura glavnog Python fajla

1. `Config` — ulazne pretpostavke i validacija.
2. `generate_market_path()` — simulira midprice, spread, volume i book depth.
3. `child_order_sizes()` — određuje koliko dionica svaka strategija izvršava u svakom intervalu.
4. `execute_order()` — računa cijene, naknade i implementation shortfall.
5. `summarize_results()` — računa mean, median, 10th/90th percentile, standard deviation, fill rates.
6. `run_simulation()` — pokreće sve scenarije, zapisuje CSV i crta grafove.
7. `main()` — prihvaća argumente s terminala.

## 10. Što objasniti na intervjuu na engleskom?

Nemoj recitirati nepoznate funkcije. Prvo ispričaj **problem → metodologiju → rezultate → rizike/ograničenja**. Zatim moraš biti sposoban objasniti: zašto dijelimo nalog, zašto nastaje spread, kako se mjeri shortfall i zašto sintetički rezultati nisu dokaz kvalitete strategije na pravom tržištu.