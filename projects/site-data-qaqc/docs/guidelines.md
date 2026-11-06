# Public comparison values

I checked these public pages on 2026-11-05 and committed three values in `src/site_data_qaqc/guidelines.json`. Each database carries the value, unit, context, source URL and check date used for that run. Runs do not download changing values from the internet.

| Matrix and chemical | Value | Published context and source |
| --- | --- | --- |
| Groundwater arsenic | 0.010 mg/L | Health Canada drinking-water maximum acceptable concentration, [arsenic guideline, section 1.0](https://www.canada.ca/en/health-canada/services/publications/healthy-living/guidelines-canadian-drinking-water-quality-guideline-technical-document-arsenic/page-2-guidelines-canadian-drinking-water-quality-guideline-technical-document-arsenic.html) |
| Groundwater benzene | 0.005 mg/L | Health Canada drinking-water maximum acceptable concentration, [benzene guideline, section 2.0](https://www.canada.ca/en/health-canada/services/publications/healthy-living/guidelines-canadian-drinking-water-quality-guideline-technical-document-benzene/page-3-guidelines-canadian-drinking-water-quality-guideline-technical-document-benzene.html) |
| Soil arsenic | 12 mg/kg dry weight | CCME residential/parkland soil, [arsenic database, Soil Quality Guidelines section](https://ccme.ca/en/chemical/9) |

I use drinking-water values as an illustrative screen for potentially potable groundwater. They are not generic contaminated-site groundwater criteria. Health Canada's arsenic guidance also calls for concentrations to be kept as low as reasonably achievable; a result below the comparison value does not imply an absence of risk. The CCME arsenic entry says soil texture differentiation is not applicable to this guideline. I require a dry-weight basis and assume residential/parkland use for this synthetic example.

These choices do not establish applicable standards for a real property. Land use, groundwater use, geology, jurisdiction, pathways, laboratory methods and current guidance need review before a real assessment. A missing guideline is labelled `no_guideline`; I do not substitute another matrix's value or use zero. Copper in the sample dataset demonstrates this case. I have not bundled soil benzene values because their applicability involves additional texture and pathway choices.

To extend the comparisons, edit the version-controlled JSON, give every entry a unique ID and matrix/chemical pair, cite the specific public source and context, and add boundary and applicability tests. The SQLite constraints reject duplicate matrix/chemical pairs. The present tool intentionally supports one fixed comparison scenario per matrix rather than silently selecting among land uses.
