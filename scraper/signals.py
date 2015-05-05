from django import dispatch


# This will be fired at end of crawling operations, when all Result
# objects are ready
post_crawl = dispatch.Signal(providing_args=["task_id"])


# Signal will be fired at the end of each scraping action in single page.
# This will be corresponded with single Result object.
post_scrape = dispatch.Signal(providing_args=["result"])
