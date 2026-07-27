# Ponte para quem não tem os experimental-features de flakes habilitados:
# `nix-shell` entrega o mesmo ambiente que `nix develop`, com as mesmas
# versões travadas no flake.lock.
(import
  (
    let
      lock = builtins.fromJSON (builtins.readFile ./flake.lock);
      node = lock.nodes.flake-compat.locked;
    in
    fetchTarball {
      url = "https://github.com/edolstra/flake-compat/archive/${node.rev}.tar.gz";
      sha256 = node.narHash;
    }
  )
  { src = ./.; }
).shellNix
