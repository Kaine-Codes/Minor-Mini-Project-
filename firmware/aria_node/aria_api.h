#pragma once

#include <ESPAsyncWebServer.h>

/** Register every contract endpoint on the server. */
void apiRegisterRoutes(AsyncWebServer &server);
