import win32com.client
try:
    sm = win32com.client.Dispatch("Search.SearchManager")
    print("SearchManager successfully dispatched!")
    print("Version:", sm.Version)
    catalog = sm.GetCatalog("SystemIndex")
    print("Catalog status:", catalog.CatalogStatus)
    crawlman = catalog.GetCrawlScopeManager()
    print("CrawlScopeManager retrieved successfully!")
except Exception as e:
    print("Error:", e)
