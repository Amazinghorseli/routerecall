# Third-party and data notices

- The repository is original RouteRecall application code released under MIT.
- Production flight search is an adapter boundary. The included `LetsFGSearch` adapter follows the [MIT-licensed LetsFG PFS contract](https://github.com/LetsFG/LetsFG), expects the provider's own bearer token, and falls back to clearly identified sample offers when no token is present. No LetsFG source code is vendored here.
- Sample passenger names, itineraries, flight numbers, prices and availability are fictional demonstration data. They are not live airline inventory.
- CockroachDB Cloud is an external service governed by Cockroach Labs' terms.
- No airline logo, proprietary booking interface, scraped dataset or copied application source is included.
