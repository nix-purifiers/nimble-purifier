# SPDX-License-Identifier: MIT
{ nimble }:
nimble.overrideAttrs (old: {
  patches = (old.patches or [ ]) ++ [ ./nimble.patch ];
})
