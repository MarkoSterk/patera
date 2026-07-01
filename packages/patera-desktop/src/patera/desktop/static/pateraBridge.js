const PATERA_DEFAULT_ENDPOINT = "/_frontend/interface";

function splitPateraArguments(args) {
  if (args.length === 0) {
    return {
      args: [],
      kwargs: {},
    };
  }

  const lastArg = args[args.length - 1];

  const lastArgIsKwargs =
    lastArg !== null &&
    typeof lastArg === "object" &&
    !Array.isArray(lastArg);

  if (!lastArgIsKwargs) {
    return {
      args,
      kwargs: {},
    };
  }

  return {
    args: args.slice(0, -1),
    kwargs: lastArg,
  };
}

async function callPateraFunction(functionName, ...rawArgs) {
  const { args, kwargs } = splitPateraArguments(rawArgs);

  const response = await fetch(PATERA_DEFAULT_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    credentials: "same-origin",
    body: JSON.stringify({
      method: functionName,
      args,
      kwargs,
    }),
  });

  let payload;

  try {
    payload = await response.json();
    return payload.data;
  } catch (error) {
    throw new Error(
      `Desktop API call '${functionName}' failed: invalid JSON response`
    );
  }
}


function createPateraProxy() {
  return new Proxy(
    {},
    {
      get(_target, property) {
        if (typeof property !== "string") {
          return undefined;
        }

        if (property === "$call") {
          return callPateraFunction;
        }

        return function pateraProxyFunction(...args) {
          return callPateraFunction(property, ...args);
        };
      },

      set() {
        throw new Error("window.patera is read-only");
      },
    }
  );
}


function installPateraBridge() {
  if (window.patera) {
    return;
  }

  window.patera = createPateraProxy();
}

installPateraBridge();
