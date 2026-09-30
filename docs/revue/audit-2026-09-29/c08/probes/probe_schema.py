from app.configs.schemas import BuilderConfig
c=BuilderConfig.model_validate({"kind":"map","bogusTop":1,"map":{"basemap":{"style":"x"},"view":{"center":[0,0],"zoom":1},
 "layers":[{"id":"l","title":"t","kind":"vector","visibleTypo":False,"symbology":{"whatever":1}}]}})
d=c.model_dump(exclude_none=True)
print("bogusTop kept:", "bogusTop" in d)
print("layer:", d["map"]["layers"][0])
