# SPDX-License-Identifier: MIT
{ nimlangserver }:
nimlangserver.overrideAttrs (old: {
  patches = (old.patches or [ ]) ++ [ ./nimlangserver.patch ];
})
