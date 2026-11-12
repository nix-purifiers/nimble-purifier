final: prev: {
  nimble-purifier = {
    readLock = import ./read-lock.nix { lib = final; };
  };
}
