"""Run script for testg app"""

if __name__ == "__main__":
    import uvicorn
    from app.configs import Config

    ##Change parameters for starting the app (host, port etc)
    ##reload=True -> watches for file changes and reloads.
    configs = Config()  # initilizes and makes defaults accessible
    uvicorn.run(
        "app:Application",
        host=configs.HOST,
        port=configs.PORT,
        lifespan=configs.LIFESPAN,
        reload=configs.DEBUG,
        factory=True,
    )
