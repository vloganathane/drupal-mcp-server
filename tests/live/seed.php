<?php

/**
 * @file
 * Seed the local DDEV site with the fixtures the live tests assume.
 *
 * Run with:  ddev drush php-script tests/live/seed.php
 *
 * Idempotent — safe to re-run after a destructive sweep. Creates an admin
 * account, a sacrificial user for destructive tools to aim at, a taxonomy
 * vocabulary with a term, and two article nodes.
 */

use Drupal\node\Entity\Node;
use Drupal\taxonomy\Entity\Term;
use Drupal\taxonomy\Entity\Vocabulary;
use Drupal\user\Entity\User;

// The sweep runs tools that block, delete, and cancel users. It must never
// be able to take the admin account down, because every later tool depends
// on that session.
$admin = User::load(1);
if ($admin && !$admin->hasRole('administrator')) {
  $admin->addRole('administrator');
  $admin->save();
  print "admin: granted administrator role\n";
}

// uid 2 is the sacrificial target: delete_user, block_user, cancel_user and
// friends aim here so they cannot destroy the real admin.
$target = User::load(2);
if (!$target) {
  $target = User::create([
    'uid' => 2,
    'name' => 'sweeptarget',
    'mail' => 'sweeptarget@example.com',
    'pass' => 'admin',
    'status' => 1,
  ]);
  $target->save();
  print "created sweeptarget (uid 2)\n";
}
elseif ($target->isBlocked()) {
  $target->setActive();
  $target->save();
  print "unblocked sweeptarget (uid 2)\n";
}

// Vocabularies and terms are config/content entities the taxonomy tools
// address by machine name and id.
$vocab = Vocabulary::load('tags');
if (!$vocab) {
  $vocab = Vocabulary::create([
    'vid' => 'tags',
    'name' => 'Tags',
  ]);
  $vocab->save();
  print "created vocabulary: tags\n";
}

$term = Term::load(1);
if (!$term) {
  $term = Term::create([
    'vid' => 'tags',
    'name' => 'sweep term',
  ]);
  $term->save();
  print "created term 1 in tags\n";
}

// Two article nodes give query_nodes, get_node, update_node, and the
// revision tools something real to address by nid.
$nids = [];
foreach (['Sweep Article Alpha', 'Sweep Article Beta'] as $title) {
  $existing = \Drupal::entityTypeManager()
    ->getStorage('node')
    ->getQuery()
    ->accessCheck(FALSE)
    ->condition('title', $title)
    ->execute();
  if ($existing) {
    $nids[] = (int) reset($existing);
    continue;
  }
  $node = Node::create([
    'type' => 'article',
    'title' => $title,
    'status' => 1,
    'uid' => 1,
  ]);
  $node->save();
  $nids[] = (int) $node->id();
}

print 'seeded nodes: ' . implode(', ', $nids) . "\n";
print "vocab: tags term: 1\n";
