# Card Behavior Index

> Auto-generated from extraction/decompiled in this repository.  
> Generated at: 2026-03-10 23:47:37 +08:00

Behavior-oriented summaries extracted from card source. Command names are intentionally kept close to code for tool-friendly lookup.

| Name | Vars | OnPlay | OnUpgrade |
| --- | --- | --- | --- |
| Abrasive | PowerVar<ThornsPower>(4m), PowerVar<DexterityPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DexterityPower>, PowerCmd.Apply<ThornsPower> | UpgradeValueBy(2m) |
| Accelerant | DynamicVar("Accelerant", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<AccelerantPower> | UpgradeValueBy(1m) |
| Accuracy | PowerVar<AccuracyPower>(4m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<AccuracyPower> | UpgradeValueBy(2m) |
| Acrobatics | CardsVar(3) | CardPileCmd.Draw, CardSelectCmd.FromHandForDiscard, CardCmd.Discard | UpgradeValueBy(1m) |
| AdaptiveStrike | DamageVar(18m, ValueProp.Move) | DamageCmd.Attack, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(5m) |
| Adrenaline | EnergyVar(1), CardsVar(2) | VfxCmd.PlayFullScreenInCombat, PlayerCmd.GainEnergy, CardPileCmd.Draw | UpgradeValueBy(1m) |
| Afterimage | PowerVar<AfterimagePower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<AfterimagePower> | AddKeyword(Innate) |
| Afterlife | SummonVar(6m) | CreatureCmd.TriggerAnim, OstyCmd.Summon | UpgradeValueBy(3m) |
| Aggression |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<AggressionPower> | AddKeyword(Innate) |
| Alchemize |  | CreatureCmd.TriggerAnim, PotionCmd.TryToProcure |  |
| Alignment | EnergyVar(2) | CreatureCmd.TriggerAnim, PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| AllForOne | DamageVar(10m, ValueProp.Move) | DamageCmd.Attack, CardPileCmd.Add | UpgradeValueBy(4m) |
| Anger | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(2m) |
| Anointed |  | CardPileCmd.Add | AddKeyword(Retain) |
| Anticipate | PowerVar<DexterityPower>(3m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<AnticipatePower> | UpgradeValueBy(2m) |
| Apotheosis |  | CardCmd.Upgrade |  |
| Apparition | PowerVar<IntangiblePower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<IntangiblePower> |  |
| Armaments | BlockVar(5m, ValueProp.Move) | CreatureCmd.GainBlock, CardCmd.Upgrade, CardSelectCmd.FromHandForUpgrade |  |
| Arsenal | PowerVar<ArsenalPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ArsenalPower> | UpgradeValueBy(1m) |
| AscendersBane |  |  |  |
| AshenStrike | CalculationBaseVar(6m), ExtraDamageVar(3m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| Assassinate | DamageVar(10m, ValueProp.Move), PowerVar<VulnerablePower>(1m) | DamageCmd.Attack, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(3m), UpgradeValueBy(1m) |
| AstralPulse | DamageVar(14m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(4m) |
| Automation | EnergyVar(1) | PowerCmd.Apply<AutomationPower> |  |
| Backflip | BlockVar(5m, ValueProp.Move), CardsVar(2) | CreatureCmd.GainBlock, CardPileCmd.Draw | UpgradeValueBy(3m) |
| Backstab | DamageVar(11m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(4m) |
| BadLuck | HpLossVar(13m) |  |  |
| BallLightning | DamageVar(7m, ValueProp.Move) | DamageCmd.Attack, OrbCmd.Channel<LightningOrb> | UpgradeValueBy(3m) |
| BansheesCry | DamageVar(33m, ValueProp.Move), EnergyVar(2) | DamageCmd.Attack | UpgradeValueBy(6m) |
| Barrage | DamageVar(5m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(2m) |
| Barricade |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<BarricadePower> |  |
| Bash | DamageVar(8m, ValueProp.Move), PowerVar<VulnerablePower>(2m) | DamageCmd.Attack, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| BattleTrance | CardsVar(3) | CardPileCmd.Draw, PowerCmd.Apply<NoDrawPower> | UpgradeValueBy(1m) |
| BeaconOfHope |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<BeaconOfHopePower> | AddKeyword(Innate) |
| BeamCell | DamageVar(3m, ValueProp.Move), PowerVar<VulnerablePower>(1m) | DamageCmd.Attack, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(1m) |
| BeatDown | CardsVar(3) | CardCmd.AutoPlay | UpgradeValueBy(1m) |
| BeatIntoShape | DamageVar(5m, ValueProp.Move), CalculationBaseVar(5m), CalculationExtraVar(5m), CalculatedVar("CalculatedForge") | DamageCmd.Attack, ForgeCmd.Forge | UpgradeValueBy(2m) |
| Beckon | HpLossVar(6m) |  |  |
| Begone | DamageVar(4m, ValueProp.Move) | DamageCmd.Attack, CardSelectCmd.FromHand, CardCmd.Upgrade, CardCmd.Transform | UpgradeValueBy(1m) |
| BelieveInYou | EnergyVar(3) | PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| BiasedCognition | PowerVar<FocusPower>(4m), PowerVar<BiasedCognitionPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<FocusPower>, PowerCmd.Apply<BiasedCognitionPower> | UpgradeValueBy(1m) |
| BigBang | CardsVar(1), EnergyVar(1), StarsVar(1), ForgeVar(5) | CreatureCmd.TriggerAnim, CardPileCmd.Draw, PlayerCmd.GainStars, PlayerCmd.GainEnergy, ForgeCmd.Forge | AddKeyword(Innate) |
| BlackHole | PowerVar<BlackHolePower>(3m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<BlackHolePower> | UpgradeValueBy(1m) |
| BladeDance | CardsVar(3) | CreatureCmd.TriggerAnim | UpgradeValueBy(1m) |
| BladeOfInk | PowerVar<StrengthPower>(2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<BladeOfInkPower> | UpgradeValueBy(1m) |
| BlightStrike | DamageVar(8m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<DoomPower> | UpgradeValueBy(2m) |
| Bloodletting | HpLossVar(3m), EnergyVar(2) | CreatureCmd.TriggerAnim, VfxCmd.PlayOnCreatureCenter, CreatureCmd.Damage, PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| BloodWall | HpLossVar(2m), BlockVar(16m, ValueProp.Move) | VfxCmd.PlayOnCreatureCenter, CreatureCmd.Damage, CreatureCmd.TriggerAnim, SfxCmd.Play, VfxCmd.PlayOnCreature, CreatureCmd.GainBlock | UpgradeValueBy(4m) |
| Bludgeon | DamageVar(32m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(10m) |
| Blur | BlockVar(5m, ValueProp.Move), DynamicVar("Blur", 1m) | CreatureCmd.GainBlock, PowerCmd.Apply<BlurPower> | UpgradeValueBy(3m) |
| Bodyguard | SummonVar(5m) | CreatureCmd.TriggerAnim, OstyCmd.Summon | UpgradeValueBy(2m) |
| BodySlam | CalculationBaseVar(0m), ExtraDamageVar(1m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack |  |
| Bolas | DamageVar(3m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| Bombardment | DamageVar(18m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(6m) |
| BoneShards | OstyDamageVar(9m, ValueProp.Move), BlockVar(9m, ValueProp.Move) | DamageCmd.Attack, CreatureCmd.GainBlock, CreatureCmd.Kill | UpgradeValueBy(3m) |
| BoostAway | BlockVar(6m, ValueProp.Move) | CreatureCmd.GainBlock, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(3m) |
| BootSequence | BlockVar(10m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| BorrowedTime | PowerVar<DoomPower>(3m), EnergyVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DoomPower>, PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| BouncingFlask | PowerVar<PoisonPower>(3m), RepeatVar(3) | CreatureCmd.TriggerAnim, PowerCmd.Apply<PoisonPower> | UpgradeValueBy(1m) |
| Brand | HpLossVar(1m), PowerVar<StrengthPower>(1m) | CreatureCmd.TriggerAnim, VfxCmd.PlayOnCreatureCenter, CreatureCmd.Damage, CardSelectCmd.FromHand, CardCmd.Exhaust, SfxCmd.Play, PowerCmd.Apply<StrengthPower> | UpgradeValueBy(1m) |
| Break | DamageVar(20m, ValueProp.Move), PowerVar<VulnerablePower>(5m) | DamageCmd.Attack, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(5m), UpgradeValueBy(2m) |
| Breakthrough | DamageVar(9m, ValueProp.Move), HpLossVar(1m) | VfxCmd.PlayOnCreatureCenter, CreatureCmd.Damage, DamageCmd.Attack | UpgradeValueBy(4m) |
| BrightestFlame | MaxHpVar(1m), EnergyVar(2), CardsVar(2) | PlayerCmd.GainEnergy, CardPileCmd.Draw, CreatureCmd.LoseMaxHp | UpgradeValueBy(1m) |
| BubbleBubble | PowerVar<PoisonPower>(9m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<PoisonPower> | UpgradeValueBy(3m) |
| Buffer | PowerVar<BufferPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<BufferPower> | UpgradeValueBy(1m) |
| BulkUp | DynamicVar("OrbSlots", 1m), PowerVar<StrengthPower>(2m), PowerVar<DexterityPower>(2m) | CreatureCmd.TriggerAnim, OrbCmd.RemoveSlots, PowerCmd.Apply<StrengthPower>, PowerCmd.Apply<DexterityPower> | UpgradeValueBy(1m) |
| BulletTime |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<NoDrawPower> |  |
| Bully | CalculationBaseVar(4m), ExtraDamageVar(2m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| Bulwark | BlockVar(13m, ValueProp.Move), ForgeVar(10) | CreatureCmd.GainBlock, CreatureCmd.TriggerAnim, ForgeCmd.Forge | UpgradeValueBy(3m) |
| BundleOfJoy | CardsVar(3) | CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(1m) |
| Burn | DamageVar(2m, ValueProp.Unpowered \\| ValueProp.Move) |  |  |
| BurningPact | CardsVar(2) | CardSelectCmd.FromHand, CardCmd.Exhaust, CreatureCmd.TriggerAnim, CardPileCmd.Draw | UpgradeValueBy(1m) |
| Burst | DynamicVar("Skills", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<BurstPower> | UpgradeValueBy(1m) |
| Bury | DamageVar(52m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(11m) |
| ByrdonisEgg |  |  |  |
| ByrdSwoop | DamageVar(14m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(4m) |
| Calamity |  | PowerCmd.Apply<CalamityPower> |  |
| Calcify | PowerVar<CalcifyPower>(4m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CalcifyPower> | UpgradeValueBy(2m) |
| CalculatedGamble |  | CardCmd.DiscardAndDraw | AddKeyword(Retain) |
| CallOfTheVoid | CardsVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CallOfTheVoidPower> | AddKeyword(Innate) |
| Caltrops | PowerVar<ThornsPower>(3m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ThornsPower> | UpgradeValueBy(2m) |
| Capacitor | RepeatVar(2) | CreatureCmd.TriggerAnim, OrbCmd.AddSlots | UpgradeValueBy(1m) |
| CaptureSpirit | DamageVar(3m, ValueProp.Unblockable \\| ValueProp.Unpowered \\| ValueProp.Move), CardsVar(3) | CreatureCmd.TriggerAnim, CreatureCmd.Damage, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardsToCombat | UpgradeValueBy(1m) |
| Cascade |  | CardPileCmd.AutoPlayFromDrawPile |  |
| Catastrophe | CardsVar(2) | CardCmd.AutoPlay | UpgradeValueBy(1m) |
| CelestialMight | DamageVar(6m, ValueProp.Move), RepeatVar(3) | DamageCmd.Attack | UpgradeValueBy(2m) |
| Chaos | RepeatVar(1) | CreatureCmd.TriggerAnim, OrbCmd.Channel | UpgradeValueBy(1m) |
| Charge | CardsVar(2) | CreatureCmd.TriggerAnim, CardSelectCmd.FromSimpleGrid, CardCmd.TransformTo<MinionStrike>, CardCmd.Upgrade |  |
| ChargeBattery | BlockVar(7m, ValueProp.Move), EnergyVar(1) | CreatureCmd.GainBlock, PowerCmd.Apply<EnergyNextTurnPower> | UpgradeValueBy(3m) |
| ChildOfTheStars | DynamicVar("BlockForStars", 2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ChildOfTheStarsPower> | UpgradeValueBy(1m) |
| Chill |  | CreatureCmd.TriggerAnim, OrbCmd.Channel<FrostOrb> |  |
| Cinder | DamageVar(17m, ValueProp.Move), DynamicVar("CardsToExhaust", 1m) | DamageCmd.Attack, CardPileCmd.ShuffleIfNecessary, CardCmd.Exhaust | UpgradeValueBy(5m) |
| Clash | DamageVar(14m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(4m) |
| Claw | DamageVar(3m, ValueProp.Move), DynamicVar("Increase", 2m) | DamageCmd.Attack | UpgradeValueBy(1m) |
| Cleanse | SummonVar(3m) | CreatureCmd.TriggerAnim, OstyCmd.Summon, CardSelectCmd.FromSimpleGrid, CardCmd.Exhaust | UpgradeValueBy(2m) |
| CloakAndDagger | BlockVar(6m, ValueProp.Move), CardsVar(1) | CreatureCmd.GainBlock | UpgradeValueBy(1m) |
| CloakOfStars | BlockVar(7m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| Clumsy |  |  |  |
| ColdSnap | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack, OrbCmd.Channel<FrostOrb> | UpgradeValueBy(3m) |
| CollisionCourse | DamageVar(9m, ValueProp.Move) | DamageCmd.Attack, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(3m) |
| Colossus | BlockVar(5m, ValueProp.Move), DynamicVar("Colossus", 1m) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<ColossusPower> | UpgradeValueBy(3m) |
| Comet | DamageVar(33m, ValueProp.Move), PowerVar<VulnerablePower>(3m), PowerVar<WeakPower>(3m) | CreatureCmd.TriggerAnim, DamageCmd.Attack, PowerCmd.Apply<WeakPower>, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(11m) |
| Compact | BlockVar(6m, ValueProp.Move) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, CardCmd.Upgrade, CardCmd.Transform | UpgradeValueBy(1m) |
| CompileDriver | DamageVar(7m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedCards") | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(3m) |
| Conflagration | CalculationBaseVar(8m), ExtraDamageVar(2m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| Conqueror | ForgeVar(3) | CreatureCmd.TriggerAnim, ForgeCmd.Forge, PowerCmd.Apply<ConquerorPower> | UpgradeValueBy(2m) |
| ConsumingShadow | RepeatVar(2), PowerVar<ConsumingShadowPower>(1m) | CreatureCmd.TriggerAnim, OrbCmd.Channel<DarkOrb>, PowerCmd.Apply<ConsumingShadowPower> | UpgradeValueBy(1m) |
| Convergence | EnergyVar(1), StarsVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<RetainHandPower>, PowerCmd.Apply<EnergyNextTurnPower>, PowerCmd.Apply<StarNextTurnPower> | UpgradeValueBy(1m) |
| Coolant | PowerVar<CoolantPower>(2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CoolantPower> | UpgradeValueBy(1m) |
| Coolheaded | CardsVar(1) | CreatureCmd.TriggerAnim, OrbCmd.Channel<FrostOrb>, CardPileCmd.Draw | UpgradeValueBy(1m) |
| Coordinate | PowerVar<StrengthPower>(5m) | PowerCmd.Apply<CoordinatePower> | UpgradeValueBy(3m) |
| CorrosiveWave | DynamicVar("CorrosiveWave", 3m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CorrosiveWavePower> | UpgradeValueBy(1m) |
| Corruption | DynamicVar("Power", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CorruptionPower> |  |
| CosmicIndifference | BlockVar(6m, ValueProp.Move) | CreatureCmd.GainBlock, CardSelectCmd.FromSimpleGrid, CardPileCmd.Add | UpgradeValueBy(3m) |
| Countdown | PowerVar<CountdownPower>(6m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CountdownPower> | UpgradeValueBy(3m) |
| CrashLanding | DamageVar(21m, ValueProp.Move) | DamageCmd.Attack, CardPileCmd.AddGeneratedCardsToCombat | UpgradeValueBy(5m) |
| CreativeAi | DynamicVar("CreativeAi", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CreativeAiPower> |  |
| CrescentSpear | CalculationBaseVar(6m), ExtraDamageVar(2m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| CrimsonMantle | PowerVar<CrimsonMantlePower>(8m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CrimsonMantlePower> | UpgradeValueBy(2m) |
| Cruelty | PowerVar<CrueltyPower>(25m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<CrueltyPower> | UpgradeValueBy(25m) |
| CrushUnder | DamageVar(7m, ValueProp.Move), DynamicVar("StrengthLoss", 1m) | CreatureCmd.TriggerAnim, DamageCmd.Attack, PowerCmd.Apply<CrushUnderPower> | UpgradeValueBy(1m) |
| CurseOfTheBell |  |  |  |
| DaggerSpray | DamageVar(4m, ValueProp.Move) | SfxCmd.Play, DamageCmd.Attack | UpgradeValueBy(2m) |
| DaggerThrow | DamageVar(9m, ValueProp.Move) | DamageCmd.Attack, CardPileCmd.Draw, CardSelectCmd.FromHandForDiscard, CardCmd.Discard | UpgradeValueBy(3m) |
| DanseMacabre | PowerVar<DanseMacabrePower>(3m), EnergyVar(2) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DanseMacabrePower> | UpgradeValueBy(1m) |
| DarkEmbrace |  | PowerCmd.Apply<DarkEmbracePower> |  |
| Darkness |  | CreatureCmd.TriggerAnim, OrbCmd.Channel<DarkOrb>, OrbCmd.Passive |  |
| DarkShackles | DynamicVar("StrengthLoss", 9m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DarkShacklesPower> | UpgradeValueBy(6m) |
| Dash | DamageVar(10m, ValueProp.Move), BlockVar(10m, ValueProp.Move) | CreatureCmd.GainBlock, DamageCmd.Attack | UpgradeValueBy(3m) |
| Dazed |  |  |  |
| DeadlyPoison | PowerVar<PoisonPower>(5m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<PoisonPower> | UpgradeValueBy(2m) |
| Deathbringer | PowerVar<DoomPower>(21m), PowerVar<WeakPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DoomPower>, PowerCmd.Apply<WeakPower> | UpgradeValueBy(5m) |
| DeathMarch | CalculationBaseVar(8m), ExtraDamageVar(3m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| DeathsDoor | BlockVar(6m, ValueProp.Move), RepeatVar(2) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock | UpgradeValueBy(1m) |
| Debilitate | DamageVar(7m, ValueProp.Move), PowerVar<DebilitatePower>(3m) | DamageCmd.Attack, PowerCmd.Apply<DebilitatePower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Debris |  |  |  |
| Debt | GoldVar(10) |  |  |
| Decay | DamageVar(2m, ValueProp.Unpowered \\| ValueProp.Move) |  |  |
| DecisionsDecisions | CardsVar(3), RepeatVar(3) | CreatureCmd.TriggerAnim, CardPileCmd.Draw, CardSelectCmd.FromHand, CardCmd.AutoPlay | UpgradeValueBy(2m) |
| DefendDefect | BlockVar(5m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| DefendIronclad | BlockVar(5m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| DefendNecrobinder | BlockVar(5m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| DefendRegent | BlockVar(5m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| DefendSilent | BlockVar(5m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| Defile | DamageVar(13m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(4m) |
| Deflect | BlockVar(4m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| Defragment | PowerVar<FocusPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<FocusPower> | UpgradeValueBy(1m) |
| Defy | BlockVar(6m, ValueProp.Move), PowerVar<WeakPower>(1m) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<WeakPower> | UpgradeValueBy(1m) |
| Delay | BlockVar(11m, ValueProp.Move), EnergyVar(1) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<EnergyNextTurnPower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Demesne | EnergyVar(1), CardsVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DemesnePower> |  |
| DemonForm | PowerVar<StrengthPower>(2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DemonFormPower> | UpgradeValueBy(1m) |
| DemonicShield | CalculationBaseVar(0m), HpLossVar(1m), CalculationExtraVar(1m), CalculatedBlockVar(ValueProp.Move) | VfxCmd.PlayOnCreatureCenter, CreatureCmd.Damage, CreatureCmd.GainBlock |  |
| DeprecatedCard |  |  |  |
| Devastate | DamageVar(30m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(10m) |
| DevourLife | PowerVar<DevourLifePower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DevourLifePower> | UpgradeValueBy(1m) |
| Dirge | SummonVar(3m) | CreatureCmd.TriggerAnim, OstyCmd.Summon, CardCmd.Upgrade, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardsToCombat | UpgradeValueBy(1m) |
| Discovery |  | CardSelectCmd.FromChooseACardScreen, CardPileCmd.AddGeneratedCardToCombat |  |
| Disintegration | PowerVar<DisintegrationPower>(6m) |  |  |
| Dismantle | DamageVar(8m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(2m) |
| Distraction |  | CardPileCmd.AddGeneratedCardToCombat |  |
| DodgeAndRoll | BlockVar(4m, ValueProp.Move) | CreatureCmd.GainBlock, PowerCmd.Apply<BlockNextTurnPower> | UpgradeValueBy(2m) |
| Dominate | DynamicVar("StrengthPerVulnerable", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<StrengthPower> |  |
| DoubleEnergy |  | PlayerCmd.GainEnergy |  |
| Doubt | PowerVar<WeakPower>(1m) |  |  |
| DrainPower | DamageVar(10m, ValueProp.Move), CardsVar(2) | DamageCmd.Attack, CardCmd.Upgrade, CardCmd.Preview | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| DramaticEntrance | DamageVar(11m, ValueProp.Move) | CreatureCmd.TriggerAnim, VfxCmd.PlayFullScreenInCombat, DamageCmd.Attack | UpgradeValueBy(4m) |
| Dredge | CardsVar(3) | CreatureCmd.TriggerAnim, CardPileCmd.Add, CardSelectCmd.FromSimpleGrid | AddKeyword(Retain) |
| DrumOfBattle | CardsVar(2), PowerVar<DrumOfBattlePower>(1m) | CardPileCmd.Draw, PowerCmd.Apply<DrumOfBattlePower> | UpgradeValueBy(1m) |
| Dualcast |  | CreatureCmd.TriggerAnim, OrbCmd.EvokeNext |  |
| DualWield | CardsVar(1) | CardSelectCmd.FromHand, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(1m) |
| DyingStar | DamageVar(9m, ValueProp.Move), DynamicVar("StrengthLoss", 9m) | CreatureCmd.TriggerAnim, DamageCmd.Attack, PowerCmd.Apply<DyingStarPower>, VfxCmd.PlayOnCreature | UpgradeValueBy(2m) |
| EchoForm | DynamicVar("EchoForm", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<EchoFormPower> |  |
| EchoingSlash | DamageVar(10m, ValueProp.Move) | CreatureCmd.Damage | UpgradeValueBy(3m) |
| Eidolon |  | CreatureCmd.TriggerAnim, CardCmd.Exhaust, PowerCmd.Apply<IntangiblePower> |  |
| EndOfDays | PowerVar<DoomPower>(29m) | CreatureCmd.TriggerAnim, VfxCmd.GetSideCenterFloor, PowerCmd.Apply<DoomPower> | UpgradeValueBy(8m) |
| EnergySurge | EnergyVar(2) | PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| EnfeeblingTouch | DynamicVar("StrengthLoss", 8m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<EnfeeblingTouchPower> | UpgradeValueBy(3m) |
| Enlightenment |  |  |  |
| Enthralled |  |  |  |
| Entrench |  | CreatureCmd.GainBlock |  |
| Entropy | CardsVar(1) | PowerCmd.Apply<EntropyPower> | AddKeyword(Innate) |
| Envenom | PowerVar<EnvenomPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<EnvenomPower> | UpgradeValueBy(1m) |
| Equilibrium | BlockVar(13m, ValueProp.Move), DynamicVar("Equilibrium", 1m) | CreatureCmd.GainBlock, PowerCmd.Apply<RetainHandPower> | UpgradeValueBy(3m) |
| Eradicate | DamageVar(11m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| EscapePlan | BlockVar(3m, ValueProp.Move) | CardPileCmd.Draw, CreatureCmd.GainBlock | UpgradeValueBy(2m) |
| EternalArmor | PowerVar<PlatingPower>(7m) | PowerCmd.Apply<PlatingPower> | UpgradeValueBy(2m) |
| EvilEye | BlockVar(8m, ValueProp.Move) | CreatureCmd.TriggerAnim, VfxCmd.PlayOnCreatureCenter, CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| ExpectAFight | EnergyVar(0), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedEnergy") | CreatureCmd.TriggerAnim, PlayerCmd.GainEnergy |  |
| Expertise | CardsVar(6) | CardPileCmd.Draw | UpgradeValueBy(1m) |
| Expose | DynamicVar("Power", 2m) | CreatureCmd.TriggerAnim, VfxCmd.PlayOnCreatureCenter, CreatureCmd.LoseBlock, PowerCmd.Remove<ArtifactPower>, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(1m) |
| Exterminate | DamageVar(3m, ValueProp.Move), RepeatVar(4) | DamageCmd.Attack | UpgradeValueBy(1m) |
| FallingStar | DamageVar(7m, ValueProp.Move), PowerVar<VulnerablePower>(1m), PowerVar<WeakPower>(1m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower>, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(4m) |
| FanOfKnives | CardsVar("Shivs", 4) | PowerCmd.Apply<FanOfKnivesPower> | UpgradeValueBy(1m) |
| Fasten | DynamicVar("ExtraBlock", 5m) | PowerCmd.Apply<FastenPower> | UpgradeValueBy(2m) |
| Fear | DamageVar(7m, ValueProp.Move), PowerVar<VulnerablePower>(1m) | DamageCmd.Attack, CreatureCmd.TriggerAnim, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(1m) |
| Feed | DamageVar(10m, ValueProp.Move), MaxHpVar(3m) | DamageCmd.Attack, CreatureCmd.GainMaxHp | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| FeedingFrenzy | PowerVar<StrengthPower>(5m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<FeedingFrenzyPower> | UpgradeValueBy(2m) |
| FeelNoPain | DynamicVar("Power", 3m) | PowerCmd.Apply<FeelNoPainPower> | UpgradeValueBy(1m) |
| Feral | PowerVar<FeralPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<FeralPower> |  |
| Fetch | OstyDamageVar(3m, ValueProp.Move), CardsVar(1) | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(3m) |
| FiendFire | DamageVar(7m, ValueProp.Move) | CardCmd.Exhaust, DamageCmd.Attack, SfxCmd.Play | UpgradeValueBy(3m) |
| FightMe | DamageVar(5m, ValueProp.Move), RepeatVar(2), PowerVar<StrengthPower>(2m), DynamicVar("EnemyStrength", 1m) | DamageCmd.Attack, PowerCmd.Apply<StrengthPower> | UpgradeValueBy(1m) |
| FightThrough | BlockVar(13m, ValueProp.Move) | CreatureCmd.GainBlock, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(4m) |
| Finesse | BlockVar(4m, ValueProp.Move), CardsVar(1) | CreatureCmd.GainBlock, CardPileCmd.Draw | UpgradeValueBy(3m) |
| Finisher | DamageVar(6m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(2m) |
| Fisticuffs | DamageVar(7m, ValueProp.Move) | DamageCmd.Attack, CreatureCmd.GainBlock | UpgradeValueBy(2m) |
| FlakCannon | DamageVar(8m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | CardCmd.Exhaust, DamageCmd.Attack | UpgradeValueBy(3m) |
| FlameBarrier | BlockVar(12m, ValueProp.Move), DynamicVar("DamageBack", 4m) | CreatureCmd.GainBlock, PowerCmd.Apply<FlameBarrierPower> | UpgradeValueBy(4m), UpgradeValueBy(2m) |
| Flanking |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<FlankingPower> |  |
| FlashOfSteel | DamageVar(5m, ValueProp.Move), CardsVar(1) | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(3m) |
| Flatten | OstyDamageVar(12m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(4m) |
| Flechettes | DamageVar(5m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(2m) |
| FlickFlack | DamageVar(7m, ValueProp.Move) | CreatureCmd.TriggerAnim, DamageCmd.Attack | UpgradeValueBy(2m) |
| FocusedStrike | DamageVar(9m, ValueProp.Move), PowerVar<FocusPower>(1m) | DamageCmd.Attack, PowerCmd.Apply<FocusedStrikePower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| FollowThrough | DamageVar(6m, ValueProp.Move), PowerVar<WeakPower>(1m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Folly |  |  |  |
| Footwork | PowerVar<DexterityPower>(2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DexterityPower> | UpgradeValueBy(1m) |
| ForbiddenGrimoire |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<ForbiddenGrimoirePower> |  |
| ForegoneConclusion | CardsVar(2) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ForegoneConclusionPower> | UpgradeValueBy(1m) |
| ForgottenRitual | EnergyVar(3) | CreatureCmd.TriggerAnim, PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| FranticEscape |  | PowerCmd.ModifyAmount |  |
| Friendship | PowerVar<StrengthPower>(2m), EnergyVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<StrengthPower>, PowerCmd.Apply<FriendshipPower> | UpgradeValueBy(-1m) |
| Ftl | DamageVar(5m, ValueProp.Move), IntVar("PlayMax", 3m), CardsVar(1) | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(1m) |
| Fuel | EnergyVar(1), CardsVar(1) | PlayerCmd.GainEnergy, CardPileCmd.Draw | UpgradeValueBy(1m) |
| Furnace | ForgeVar(4) | CreatureCmd.TriggerAnim, PowerCmd.Apply<FurnacePower> | UpgradeValueBy(2m) |
| Fusion |  | CreatureCmd.TriggerAnim, OrbCmd.Channel<PlasmaOrb> |  |
| GammaBlast | DamageVar(13m, ValueProp.Move), PowerVar<VulnerablePower>(2m), PowerVar<WeakPower>(2m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower>, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(5m) |
| GangUp | CalculationBaseVar(5m), ExtraDamageVar(5m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(2m) |
| GatherLight | BlockVar(7m, ValueProp.Move), StarsVar(1) | CreatureCmd.GainBlock, PlayerCmd.GainStars | UpgradeValueBy(3m) |
| Genesis | DynamicVar("StarsPerTurn", 2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<GenesisPower> | UpgradeValueBy(1m) |
| GeneticAlgorithm | BlockVar(CurrentBlock, ValueProp.Move), IntVar("Increase", 3m) | CreatureCmd.GainBlock | UpgradeValueBy(1m) |
| GiantRock | DamageVar(16m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(4m) |
| Glacier | BlockVar(6m, ValueProp.Move) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, OrbCmd.Channel<FrostOrb> | UpgradeValueBy(3m) |
| Glasswork | BlockVar(5m, ValueProp.Move) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, OrbCmd.Channel<GlassOrb> | UpgradeValueBy(3m) |
| Glimmer | CardsVar(3), DynamicVar("PutBack", 1m) | CardPileCmd.Draw, CardSelectCmd.FromHand, CardPileCmd.Add | UpgradeValueBy(1m) |
| GlimpseBeyond | CardsVar(3) | CardPileCmd.AddGeneratedCardsToCombat, CardCmd.PreviewCardPileAdd | UpgradeValueBy(1m) |
| Glitterstream | BlockVar(11m, ValueProp.Move), BlockVar("BlockNextTurn", 4m, ValueProp.Move) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<BlockNextTurnPower> | UpgradeValueBy(2m) |
| Glow | StarsVar(1), CardsVar(2) | CreatureCmd.TriggerAnim, PlayerCmd.GainStars, CardPileCmd.Draw | UpgradeValueBy(1m) |
| GoForTheEyes | DamageVar(3m, ValueProp.Move), PowerVar<WeakPower>(1m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower> | UpgradeValueBy(1m) |
| GoldAxe | CalculationBaseVar(0m), ExtraDamageVar(1m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | AddKeyword(Retain) |
| GrandFinale | DamageVar(50m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(10m) |
| Grapple | DamageVar(7m, ValueProp.Move), PowerVar<GrapplePower>(5m) | DamageCmd.Attack, PowerCmd.Apply<GrapplePower> | UpgradeValueBy(2m) |
| Graveblast | DamageVar(4m, ValueProp.Move) | DamageCmd.Attack, CardSelectCmd.FromSimpleGrid, CardPileCmd.Add | UpgradeValueBy(2m) |
| GraveWarden | BlockVar(8m, ValueProp.Move), CardsVar(1) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, CardCmd.Upgrade, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardsToCombat | UpgradeValueBy(2m) |
| Greed |  |  |  |
| Guards |  | CreatureCmd.TriggerAnim, CardSelectCmd.FromHand, CardCmd.Upgrade, CardCmd.Transform |  |
| GuidingStar | DamageVar(12m, ValueProp.Move), CardsVar(2) | CreatureCmd.TriggerAnim, SfxCmd.Play, DamageCmd.Attack, PowerCmd.Apply<DrawCardsNextTurnPower> | UpgradeValueBy(1m) |
| Guilty | DynamicVar("Combats", 5m) |  |  |
| GunkUp | DamageVar(4m, ValueProp.Move), RepeatVar(3) | DamageCmd.Attack, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(1m) |
| Hailstorm | PowerVar<HailstormPower>(6m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<HailstormPower> | UpgradeValueBy(2m) |
| HammerTime |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<HammerTimePower> |  |
| HandOfGreed | DamageVar(20m, ValueProp.Move), DynamicVar("Gold", 20m) | DamageCmd.Attack, VfxCmd.PlayVfx, PlayerCmd.GainGold | UpgradeValueBy(5m) |
| HandTrick | BlockVar(7m, ValueProp.Move) | CreatureCmd.GainBlock, CardSelectCmd.FromHand, CardCmd.ApplySingleTurnSly | UpgradeValueBy(3m) |
| Hang | DamageVar(10m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<HangPower> | UpgradeValueBy(3m) |
| Haunt | HpLossVar(6m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<HauntPower> | UpgradeValueBy(2m) |
| Havoc |  | CardPileCmd.AutoPlayFromDrawPile |  |
| Haze | PowerVar<PoisonPower>(4m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<PoisonPower> | UpgradeValueBy(2m) |
| Headbutt | DamageVar(9m, ValueProp.Move) | DamageCmd.Attack, CardSelectCmd.FromSimpleGrid, CardPileCmd.Add | UpgradeValueBy(3m) |
| HeavenlyDrill | DamageVar(8m, ValueProp.Move), EnergyVar(4) | DamageCmd.Attack | UpgradeValueBy(2m) |
| Hegemony | DamageVar(15m, ValueProp.Move), EnergyVar(2) | DamageCmd.Attack, PowerCmd.Apply<EnergyNextTurnPower> | UpgradeValueBy(3m), UpgradeValueBy(1m) |
| HeirloomHammer | DamageVar(17m, ValueProp.Move), RepeatVar(1) | DamageCmd.Attack, CardSelectCmd.FromHand, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(5m) |
| HelixDrill | DamageVar(3m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(2m) |
| HelloWorld |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<HelloWorldPower> | AddKeyword(Innate) |
| Hellraiser |  | PowerCmd.Apply<HellraiserPower> |  |
| Hemokinesis | HpLossVar(2m), DamageVar(14m, ValueProp.Move) | CreatureCmd.Damage, DamageCmd.Attack | UpgradeValueBy(5m) |
| HiddenCache | StarsVar(1), PowerVar<StarNextTurnPower>(3m) | CreatureCmd.TriggerAnim, PlayerCmd.GainStars, PowerCmd.Apply<StarNextTurnPower> | UpgradeValueBy(1m) |
| HiddenDaggers | CardsVar(2), DynamicVar("Shivs", 2m) | CardCmd.Discard, CardSelectCmd.FromHandForDiscard, CardCmd.Upgrade |  |
| HiddenGem | IntVar("Replay", 2m) | CreatureCmd.TriggerAnim, CardCmd.Preview | UpgradeValueBy(1m) |
| HighFive | OstyDamageVar(11m, ValueProp.Move), PowerVar<VulnerablePower>(2m) | DamageCmd.Attack, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Hologram | BlockVar(3m, ValueProp.Move) | CreatureCmd.GainBlock, CardSelectCmd.FromSimpleGrid, CardPileCmd.Add | UpgradeValueBy(2m) |
| Hotfix | PowerVar<FocusPower>(2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<HotfixPower> | UpgradeValueBy(1m) |
| HowlFromBeyond | DamageVar(16m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(5m) |
| HuddleUp | CardsVar(2) | CardPileCmd.Draw | UpgradeValueBy(1m) |
| Hyperbeam | DamageVar(26m, ValueProp.Move), PowerVar<FocusPower>(3m) | DamageCmd.Attack, PowerCmd.Apply<FocusPower> | UpgradeValueBy(8m) |
| IAmInvincible | BlockVar(9m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| IceLance | DamageVar(19m, ValueProp.Move), RepeatVar(3) | DamageCmd.Attack, OrbCmd.Channel<FrostOrb> | UpgradeValueBy(5m) |
| Ignition |  | CreatureCmd.TriggerAnim, OrbCmd.Channel<PlasmaOrb> |  |
| Impatience | CardsVar(2) | CardPileCmd.Draw | UpgradeValueBy(1m) |
| Impervious | BlockVar(30m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(10m) |
| Infection | DamageVar(3m, ValueProp.Unpowered \\| ValueProp.Move) |  |  |
| InfernalBlade |  | CardPileCmd.AddGeneratedCardToCombat |  |
| Inferno | PowerVar<InfernoPower>(6m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<InfernoPower> | UpgradeValueBy(3m) |
| InfiniteBlades |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<InfiniteBladesPower> | AddKeyword(Innate) |
| Inflame | PowerVar<StrengthPower>(2m) | PowerCmd.Apply<StrengthPower> | UpgradeValueBy(1m) |
| Injury |  |  |  |
| Intercept | BlockVar(9m, ValueProp.Move) | CreatureCmd.GainBlock, PowerCmd.Apply<CoveredPower> | UpgradeValueBy(4m) |
| Invoke | SummonVar(2m), EnergyVar(2) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SummonNextTurnPower>, PowerCmd.Apply<EnergyNextTurnPower> | UpgradeValueBy(1m) |
| IronWave | DamageVar(5m, ValueProp.Move), BlockVar(5m, ValueProp.Move) | CreatureCmd.GainBlock, DamageCmd.Attack | UpgradeValueBy(2m) |
| Iteration | PowerVar<IterationPower>(2m) | PowerCmd.Apply<IterationPower> | UpgradeValueBy(1m) |
| JackOfAllTrades | CardsVar(1) | CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(1m) |
| Jackpot | DamageVar(25m, ValueProp.Move), CardsVar(3) | DamageCmd.Attack, CardCmd.Upgrade, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(5m) |
| Juggernaut | PowerVar<JuggernautPower>(5m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<JuggernautPower> | UpgradeValueBy(2m) |
| Juggling |  | PowerCmd.Apply<JugglingPower> | AddKeyword(Innate) |
| KinglyKick | DamageVar(24m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(6m) |
| KinglyPunch | DamageVar(8m, ValueProp.Move), DynamicVar("Increase", 3m) | DamageCmd.Attack | UpgradeValueBy(2m) |
| KnifeTrap | CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedShivs") | CardCmd.Upgrade, CardCmd.AutoPlay |  |
| Knockdown | DamageVar(10m, ValueProp.Move), PowerVar<KnockdownPower>(2m) | DamageCmd.Attack, PowerCmd.Apply<KnockdownPower> | UpgradeValueBy(4m), UpgradeValueBy(1m) |
| KnockoutBlow | DamageVar(30m, ValueProp.Move), StarsVar(5) | DamageCmd.Attack, PlayerCmd.GainStars | UpgradeValueBy(8m) |
| KnowThyPlace | PowerVar<WeakPower>(1m), PowerVar<VulnerablePower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<WeakPower>, PowerCmd.Apply<VulnerablePower> |  |
| LanternKey |  |  |  |
| Largesse |  | CreatureCmd.TriggerAnim, CardCmd.Upgrade, CardPileCmd.AddGeneratedCardToCombat |  |
| LeadingStrike | CardsVar("Shivs", 1), DamageVar(7m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Leap | BlockVar(9m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| LegionOfBone | SummonVar(6m) | CreatureCmd.TriggerAnim, OstyCmd.Summon | UpgradeValueBy(2m) |
| LegSweep | BlockVar(11m, ValueProp.Move), PowerVar<WeakPower>(2m) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<WeakPower> | UpgradeValueBy(3m), UpgradeValueBy(1m) |
| Lethality | PowerVar<LethalityPower>(50m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<LethalityPower> | UpgradeValueBy(25m) |
| Lift | BlockVar(11m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(5m) |
| LightningRod | BlockVar(4m, ValueProp.Move), PowerVar<LightningRodPower>(2m) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<LightningRodPower> | UpgradeValueBy(3m) |
| Loop | DynamicVar("Loop", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<LoopPower> | UpgradeValueBy(1m) |
| Luminesce | EnergyVar(2) | CreatureCmd.TriggerAnim, PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| LunarBlast | DamageVar(4m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(1m) |
| MachineLearning | CardsVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<MachineLearningPower> | AddKeyword(Innate) |
| MadScience | DamageVar(12m, ValueProp.Move), BlockVar(8m, ValueProp.Move), PowerVar<WeakPower>("SappingWeak", 2m), PowerVar<VulnerablePower>("SappingVulnerable", 2m), DynamicVar("ViolenceHits", 3m), PowerVar<StranglePower>("ChokingDamage", 6m), EnergyVar("EnergizedEnergy", 2), CardsVar("WisdomCards", 3), PowerVar<StrengthPower>("ExpertiseStrength", 2m), PowerVar<DexterityPower>("ExpertiseDexterity", 2m), DynamicVar("CuriousReduction", 1m) |  | AddKeyword(Innate) |
| MakeItSo | DamageVar(6m, ValueProp.Move), CardsVar(3) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Malaise |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<StrengthPower>, PowerCmd.Apply<WeakPower> |  |
| Mangle | DamageVar(15m, ValueProp.Move), DynamicVar("StrengthLoss", 10m) | DamageCmd.Attack, PowerCmd.Apply<ManglePower> | UpgradeValueBy(5m) |
| ManifestAuthority | BlockVar(7m, ValueProp.Move) | CreatureCmd.GainBlock, CardCmd.Upgrade, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(1m) |
| MasterOfStrategy | CardsVar(3) | CardPileCmd.Draw | UpgradeValueBy(1m) |
| MasterPlanner |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<MasterPlannerPower> |  |
| Maul | DamageVar(5m, ValueProp.Move), DynamicVar("Increase", 1m) | DamageCmd.Attack | UpgradeValueBy(1m) |
| Mayhem |  | PowerCmd.Apply<MayhemPower> |  |
| Melancholy | BlockVar(13m, ValueProp.Move), EnergyVar(1) | CreatureCmd.GainBlock | UpgradeValueBy(4m) |
| MementoMori | CalculationBaseVar(8m), ExtraDamageVar(4m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Metamorphosis | CardsVar(3) | CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(2m) |
| MeteorShower | DamageVar(14m, ValueProp.Move), PowerVar<VulnerablePower>(2m), PowerVar<WeakPower>(2m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower>, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(7m) |
| MeteorStrike | DamageVar(24m, ValueProp.Move) | DamageCmd.Attack, OrbCmd.Channel<PlasmaOrb> | UpgradeValueBy(6m) |
| Mimic | CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedBlockVar(ValueProp.Move) | CreatureCmd.GainBlock |  |
| MindBlast | CalculationBaseVar(0m), ExtraDamageVar(1m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack |  |
| MindRot | PowerVar<MindRotPower>(1m) |  |  |
| MinionDiveBomb | DamageVar(13m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| MinionSacrifice | BlockVar(9m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| MinionStrike | DamageVar(7m, ValueProp.Move), CardsVar(1) | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(3m) |
| Mirage | CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedBlockVar(ValueProp.Move) | CreatureCmd.GainBlock |  |
| Misery | DamageVar(7m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.ModifyAmount, PowerCmd.Apply | UpgradeValueBy(2m), AddKeyword(Retain) |
| Modded | RepeatVar(1), CardsVar(1) | CreatureCmd.TriggerAnim, OrbCmd.AddSlots, CardPileCmd.Draw | UpgradeValueBy(1m) |
| MoltenFist | DamageVar(10m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(4m) |
| MomentumStrike | DamageVar(10m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| MonarchsGaze | DynamicVar("StrengthLoss", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<MonarchsGazePower> |  |
| Monologue | DynamicVar("Power", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<MonologuePower> | AddKeyword(Retain) |
| MultiCast |  | CreatureCmd.TriggerAnim, OrbCmd.EvokeNext |  |
| Murder | CalculationBaseVar(1m), ExtraDamageVar(1m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack |  |
| NecroMastery | SummonVar(5m) | CreatureCmd.TriggerAnim, OstyCmd.Summon, PowerCmd.Apply<NecroMasteryPower> | UpgradeValueBy(3m) |
| NegativePulse | BlockVar(5m, ValueProp.Move), PowerVar<DoomPower>(7m) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<DoomPower> | UpgradeValueBy(1m), UpgradeValueBy(4m) |
| NeowsFury | DamageVar(10m, ValueProp.Move), CardsVar(2) | DamageCmd.Attack, CardPileCmd.Add | UpgradeValueBy(4m) |
| Neurosurge | PowerVar<NeurosurgePower>(3m), EnergyVar(3), CardsVar(2) | CreatureCmd.TriggerAnim, PlayerCmd.GainEnergy, CardPileCmd.Draw, PowerCmd.Apply<NeurosurgePower> | UpgradeValueBy(1m) |
| Neutralize | DamageVar(3m, ValueProp.Move), PowerVar<WeakPower>(1m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower> | UpgradeValueBy(1m) |
| NeutronAegis | PowerVar<PlatingPower>(8m) | PowerCmd.Apply<PlatingPower> | UpgradeValueBy(3m) |
| Nightmare |  | CreatureCmd.TriggerAnim, CardSelectCmd.FromHand, PowerCmd.Apply<NightmarePower> |  |
| NoEscape | DynamicVar("DoomThreshold", 10m), CalculationBaseVar(10m), CalculationExtraVar(5m), CalculatedVar("CalculatedDoom") | PowerCmd.Apply<DoomPower> | UpgradeValueBy(5m) |
| Normality | CalculationBaseVar(3m), CalculationExtraVar(-1m), CalculatedVar("CalculatedCards") |  |  |
| Nostalgia |  | PowerCmd.Apply<NostalgiaPower> |  |
| NoxiousFumes | DynamicVar("PoisonPerTurn", 2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<NoxiousFumesPower> | UpgradeValueBy(1m) |
| Null | DamageVar(10m, ValueProp.Move), PowerVar<WeakPower>(2m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower>, OrbCmd.Channel<DarkOrb> | UpgradeValueBy(3m), UpgradeValueBy(1m) |
| Oblivion | PowerVar<DoomPower>(3m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<OblivionPower> | UpgradeValueBy(1m) |
| Offering | HpLossVar(6m), EnergyVar(2), CardsVar(3) | CreatureCmd.Damage, PlayerCmd.GainEnergy, CardPileCmd.Draw | UpgradeValueBy(2m) |
| Omnislice | DamageVar(8m, ValueProp.Move) | CreatureCmd.Damage | UpgradeValueBy(3m) |
| OneTwoPunch | DynamicVar("Attacks", 1m) | PowerCmd.Apply<OneTwoPunchPower> | UpgradeValueBy(1m) |
| Orbit | EnergyVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<OrbitPower> |  |
| Outbreak | PowerVar<OutbreakPower>(11m), RepeatVar(3) | PowerCmd.Apply<OutbreakPower> | UpgradeValueBy(4m) |
| Outmaneuver | EnergyVar(2) | PowerCmd.Apply<EnergyNextTurnPower> | UpgradeValueBy(1m) |
| Overclock | CardsVar(2) | CreatureCmd.TriggerAnim, CardPileCmd.Draw, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(1m) |
| PactsEnd | DamageVar(17m, ValueProp.Move), CardsVar(3) | DamageCmd.Attack | UpgradeValueBy(6m) |
| Pagestorm | CardsVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<PagestormPower> |  |
| PaleBlueDot | CardsVar(1), DynamicVar("CardPlay", 5m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<PaleBlueDotPower> | UpgradeValueBy(1m) |
| Panache | DynamicVar("PanacheDamage", 10m) | PowerCmd.Apply<PanachePower> | UpgradeValueBy(4m) |
| PanicButton | BlockVar(30m, ValueProp.Move), DynamicVar("Turns", 2m) | CreatureCmd.GainBlock, PowerCmd.Apply<NoBlockPower> | UpgradeValueBy(10m) |
| Parry | PowerVar<ParryPower>(6m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ParryPower> | UpgradeValueBy(3m) |
| Parse | CardsVar(3) | CardPileCmd.Draw | UpgradeValueBy(1m) |
| ParticleWall | BlockVar(9m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| Patter | BlockVar(8m, ValueProp.Move), PowerVar<VigorPower>(2m) | CreatureCmd.GainBlock, CreatureCmd.TriggerAnim, PowerCmd.Apply<VigorPower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Peck | DamageVar(2m, ValueProp.Move), RepeatVar(3) | DamageCmd.Attack | UpgradeValueBy(1m) |
| PerfectedStrike | CalculationBaseVar(6m), ExtraDamageVar(2m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| PhantomBlades | PowerVar<PhantomBladesPower>(9m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<PhantomBladesPower> | UpgradeValueBy(3m) |
| PhotonCut | DamageVar(10m, ValueProp.Move), CardsVar(1), DynamicVar("PutBack", 1m) | DamageCmd.Attack, CardPileCmd.Draw, CardPileCmd.Add, CardSelectCmd.FromHand | UpgradeValueBy(3m), UpgradeValueBy(1m) |
| PiercingWail | DynamicVar("StrengthLoss", 6m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<PiercingWailPower> | UpgradeValueBy(2m) |
| Pillage | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(3m) |
| PillarOfCreation | BlockVar(3m, ValueProp.Unpowered) | PowerCmd.Apply<PillarOfCreationPower> | UpgradeValueBy(1m) |
| Pinpoint | DamageVar(17m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(5m) |
| PoisonedStab | DamageVar(6m, ValueProp.Move), PowerVar<PoisonPower>(3m) | DamageCmd.Attack, PowerCmd.Apply<PoisonPower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Poke | OstyDamageVar(6m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| PommelStrike | DamageVar(9m, ValueProp.Move), CardsVar(1) | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(1m) |
| PoorSleep |  |  |  |
| Pounce | DamageVar(12m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<FreeSkillPower> | UpgradeValueBy(6m) |
| PreciseCut | CalculationBaseVar(13m), ExtraDamageVar(2m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Predator | DamageVar(15m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<DrawCardsNextTurnPower> | UpgradeValueBy(5m) |
| Prepared | CardsVar(1) | CardPileCmd.Draw, CardCmd.Discard, CardSelectCmd.FromHandForDiscard | UpgradeValueBy(1m) |
| PrepTime | PowerVar<PrepTimePower>(4m) | PowerCmd.Apply<PrepTimePower> | UpgradeValueBy(2m) |
| PrimalForce |  | CreatureCmd.TriggerAnim, CardCmd.Upgrade, CardCmd.Transform |  |
| Production | EnergyVar(2) | PlayerCmd.GainEnergy |  |
| Prolong |  | PowerCmd.Apply<BlockNextTurnPower> |  |
| Prophesize | CardsVar(6) | CreatureCmd.TriggerAnim, CardPileCmd.Draw | UpgradeValueBy(3m) |
| Protector | CalculationBaseVar(10m), ExtraDamageVar(1m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(5m) |
| Prowess | PowerVar<StrengthPower>(1m), PowerVar<DexterityPower>(1m) | PowerCmd.Apply<StrengthPower>, PowerCmd.Apply<DexterityPower> | UpgradeValueBy(1m) |
| PullAggro | SummonVar(4m), BlockVar(7m, ValueProp.Move) | CreatureCmd.TriggerAnim, OstyCmd.Summon, CreatureCmd.GainBlock | UpgradeValueBy(1m), UpgradeValueBy(2m) |
| PullFromBelow | DamageVar(5m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(2m) |
| Purity | CardsVar(3) | CardSelectCmd.FromHand, CardCmd.Exhaust | UpgradeValueBy(2m) |
| Putrefy | DynamicVar("Power", 2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<WeakPower>, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(1m) |
| Pyre | EnergyVar(1) | PowerCmd.Apply<PyrePower> | UpgradeValueBy(1m) |
| Quadcast | RepeatVar(4) | CreatureCmd.TriggerAnim, OrbCmd.EvokeNext |  |
| Quasar |  | CardCmd.Upgrade, CardSelectCmd.FromChooseACardScreen, CardPileCmd.AddGeneratedCardToCombat |  |
| Radiate | DamageVar(3m, ValueProp.Move), StarsVar(1), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(1m) |
| Rage | DynamicVar("Power", 3m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<RagePower> | UpgradeValueBy(2m) |
| Rainbow |  | CreatureCmd.TriggerAnim, OrbCmd.Channel<LightningOrb>, OrbCmd.Channel<FrostOrb>, OrbCmd.Channel<DarkOrb> |  |
| Rally | BlockVar(12m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(5m) |
| Rampage | DamageVar(9m, ValueProp.Move), DynamicVar("Increase", 5m) | DamageCmd.Attack | UpgradeValueBy(4m) |
| Rattle | OstyDamageVar(7m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(2m) |
| Reanimate | SummonVar(20m) | CreatureCmd.TriggerAnim, OstyCmd.Summon | UpgradeValueBy(5m) |
| Reap | DamageVar(27m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(6m) |
| ReaperForm |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<ReaperFormPower> | AddKeyword(Retain) |
| Reave | DamageVar(9m, ValueProp.Move), CardsVar(1) | DamageCmd.Attack, CardCmd.Upgrade, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardsToCombat | UpgradeValueBy(2m) |
| Reboot | CardsVar(4) | CreatureCmd.TriggerAnim, CardPileCmd.Add, CardPileCmd.Shuffle, CardPileCmd.Draw | UpgradeValueBy(2m) |
| Rebound | DamageVar(9m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<ReboundPower> | UpgradeValueBy(3m) |
| RefineBlade | ForgeVar(6), EnergyVar(1) | CreatureCmd.TriggerAnim, ForgeCmd.Forge, PowerCmd.Apply<EnergyNextTurnPower> | UpgradeValueBy(4m) |
| Reflect | BlockVar(17m, ValueProp.Move) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<ReflectPower> | UpgradeValueBy(4m) |
| Reflex | CardsVar(2) | CreatureCmd.TriggerAnim, CardPileCmd.Draw | UpgradeValueBy(1m) |
| Refract | RepeatVar(2), DamageVar(9m, ValueProp.Move) | DamageCmd.Attack, OrbCmd.Channel<GlassOrb> | UpgradeValueBy(3m) |
| Regret |  |  |  |
| Relax | BlockVar(15m, ValueProp.Move), CardsVar(2), EnergyVar(2) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<DrawCardsNextTurnPower>, PowerCmd.Apply<EnergyNextTurnPower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Rend | CalculationBaseVar(15m), ExtraDamageVar(5m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Resonance | PowerVar<StrengthPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<StrengthPower> | UpgradeValueBy(1m) |
| Restlessness | CardsVar(2), EnergyVar(2) | CardPileCmd.Draw, PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| Ricochet | DamageVar(3m, ValueProp.Move), RepeatVar(4) | DamageCmd.Attack | UpgradeValueBy(1m) |
| RightHandHand | OstyDamageVar(4m, ValueProp.Move), EnergyVar(2) | DamageCmd.Attack | UpgradeValueBy(2m) |
| RipAndTear | DamageVar(7m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(2m) |
| RocketPunch | DamageVar(13m, ValueProp.Move), CardsVar(1) | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(1m) |
| RollingBoulder | PowerVar<RollingBoulderPower>(5m), DynamicVar("IncrementAmount", 5m) | PowerCmd.Apply<RollingBoulderPower> | UpgradeValueBy(5m) |
| RoyalGamble | StarsVar(9) | CreatureCmd.TriggerAnim, PlayerCmd.GainStars | AddKeyword(Retain) |
| Royalties | GoldVar(30) | CreatureCmd.TriggerAnim, PowerCmd.Apply<RoyaltiesPower> | UpgradeValueBy(5m) |
| Rupture | PowerVar<StrengthPower>(1m) | PowerCmd.Apply<RupturePower> | UpgradeValueBy(1m) |
| Sacrifice |  | CreatureCmd.TriggerAnim, CreatureCmd.Kill, CreatureCmd.GainBlock |  |
| Salvo | DamageVar(12m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<RetainHandPower> | UpgradeValueBy(4m) |
| Scavenge | EnergyVar(2) | CardSelectCmd.FromHand, CardCmd.Exhaust, PowerCmd.Apply<EnergyNextTurnPower> | UpgradeValueBy(1m) |
| Scourge | PowerVar<DoomPower>(13m), CardsVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<DoomPower>, CardPileCmd.Draw | UpgradeValueBy(3m), UpgradeValueBy(1m) |
| Scrape | DamageVar(7m, ValueProp.Move), CardsVar(4) | DamageCmd.Attack, CardPileCmd.Draw, CardCmd.Discard | UpgradeValueBy(3m), UpgradeValueBy(1m) |
| Scrawl |  | CardPileCmd.Draw | AddKeyword(Retain) |
| SculptingStrike | DamageVar(8m, ValueProp.Move) | DamageCmd.Attack, CardSelectCmd.FromHand, CardCmd.ApplyKeyword | UpgradeValueBy(3m) |
| Seance | CardsVar(1) | CreatureCmd.TriggerAnim, CardSelectCmd.FromSimpleGrid, CardCmd.TransformTo<Soul>, CardCmd.Upgrade |  |
| SecondWind | BlockVar(5m, ValueProp.Move) | CreatureCmd.TriggerAnim, CardCmd.Exhaust, CreatureCmd.GainBlock | UpgradeValueBy(2m) |
| SecretTechnique |  | CardSelectCmd.FromSimpleGrid, CardPileCmd.Add |  |
| SecretWeapon |  | CardSelectCmd.FromSimpleGrid, CardPileCmd.Add |  |
| SeekerStrike | DamageVar(6m, ValueProp.Move), CardsVar(3) | DamageCmd.Attack, CardSelectCmd.FromSimpleGrid, CardPileCmd.Add | UpgradeValueBy(3m) |
| SeekingEdge | ForgeVar(7) | CreatureCmd.TriggerAnim, ForgeCmd.Forge, PowerCmd.Apply<SeekingEdgePower> | UpgradeValueBy(4m) |
| SentryMode | PowerVar<SentryModePower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SentryModePower> |  |
| SerpentForm | PowerVar<SerpentFormPower>(4m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SerpentFormPower> | UpgradeValueBy(1m) |
| SetupStrike | DamageVar(7m, ValueProp.Move), PowerVar<StrengthPower>(2m) | DamageCmd.Attack, PowerCmd.Apply<SetupStrikePower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| SevenStars | DamageVar(7m, ValueProp.Move), RepeatVar(7) | DamageCmd.Attack |  |
| Severance | DamageVar(13m, ValueProp.Move) | DamageCmd.Attack, CardPileCmd.AddGeneratedCardToCombat, CardCmd.PreviewCardPileAdd | UpgradeValueBy(5m) |
| Shadowmeld | DynamicVar("Power", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ShadowmeldPower> |  |
| ShadowShield | BlockVar(11m, ValueProp.Move) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, OrbCmd.Channel<DarkOrb> | UpgradeValueBy(4m) |
| ShadowStep | CardsVar(3) | CardCmd.Discard, PowerCmd.Apply<ShadowStepPower> |  |
| Shame | DynamicVar("Frail", 1m) |  |  |
| SharedFate | DynamicVar("EnemyStrengthLoss", 2m), DynamicVar("PlayerStrengthLoss", 2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<StrengthPower> | UpgradeValueBy(1m) |
| Shatter | DamageVar(11m, ValueProp.Move) | DamageCmd.Attack, OrbCmd.EvokeNext | UpgradeValueBy(4m) |
| ShiningStrike | DamageVar(8m, ValueProp.Move), StarsVar(2) | DamageCmd.Attack, PlayerCmd.GainStars, CardPileCmd.Add | UpgradeValueBy(3m) |
| Shiv | DamageVar(4m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("FanOfKnivesAmount") | DamageCmd.Attack | UpgradeValueBy(2m) |
| Shockwave | DynamicVar("Power", 3m) | CreatureCmd.TriggerAnim, VfxCmd.PlayOnCreatureCenter, PowerCmd.Apply<WeakPower>, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(2m) |
| Shroud | BlockVar(2m, ValueProp.Unpowered) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ShroudPower> | UpgradeValueBy(1m) |
| ShrugItOff | BlockVar(8m, ValueProp.Move), CardsVar(1) | CreatureCmd.GainBlock, CardPileCmd.Draw | UpgradeValueBy(3m) |
| SicEm | OstyDamageVar(5m, ValueProp.Move), PowerVar<SicEmPower>(2m) | DamageCmd.Attack, PowerCmd.Apply<SicEmPower> | UpgradeValueBy(1m) |
| SignalBoost | PowerVar<SignalBoostPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SignalBoostPower> |  |
| Skewer | DamageVar(7m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Skim | CardsVar(3) | CardPileCmd.Draw | UpgradeValueBy(1m) |
| SleightOfFlesh | PowerVar<SleightOfFleshPower>(9m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SleightOfFleshPower> | UpgradeValueBy(4m) |
| Slice | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Slimed | CardsVar(1) | CardPileCmd.Draw |  |
| Sloth | PowerVar<SlothPower>(3m) |  |  |
| Smokestack | PowerVar<SmokestackPower>(5m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SmokestackPower> | UpgradeValueBy(2m) |
| Snakebite | PowerVar<PoisonPower>(7m) | CreatureCmd.TriggerAnim, VfxCmd.PlayOnCreatureCenter, PowerCmd.Apply<PoisonPower> | UpgradeValueBy(3m) |
| Snap | OstyDamageVar(7m, ValueProp.Move) | DamageCmd.Attack, CardSelectCmd.FromHand, CardCmd.ApplyKeyword | UpgradeValueBy(3m) |
| Sneaky | PowerVar<SneakyPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SneakyPower> | UpgradeValueBy(1m) |
| SolarStrike | DamageVar(8m, ValueProp.Move), StarsVar(1) | DamageCmd.Attack, PlayerCmd.GainStars | UpgradeValueBy(1m) |
| Soot |  |  |  |
| Soul | CardsVar(2) | CardPileCmd.Draw | UpgradeValueBy(1m) |
| SoulStorm | CalculationBaseVar(9m), ExtraDamageVar(2m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| SovereignBlade | DamageVar(10m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("SeekingEdgeAmount"), RepeatVar(1) | DamageCmd.Attack |  |
| Sow | DamageVar(8m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| SpectrumShift | CardsVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SpectrumShiftPower> |  |
| Speedster | PowerVar<SpeedsterPower>(2m) | PowerCmd.Apply<SpeedsterPower> | UpgradeValueBy(1m) |
| Spinner | PowerVar<SpinnerPower>(1m) | CreatureCmd.TriggerAnim, OrbCmd.Channel<GlassOrb>, PowerCmd.Apply<SpinnerPower> |  |
| SpiritOfAsh | DynamicVar("BlockOnExhaust", 4m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SpiritOfAshPower> | UpgradeValueBy(1m) |
| Spite | DamageVar(6m, ValueProp.Move), CardsVar(1) | DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(3m) |
| Splash |  | CardCmd.Upgrade, CardSelectCmd.FromChooseACardScreen, CardPileCmd.AddGeneratedCardToCombat |  |
| SpoilsMap | GoldVar(600) |  |  |
| SpoilsOfBattle | ForgeVar(10) | ForgeCmd.Forge | UpgradeValueBy(5m) |
| SporeMind |  |  |  |
| Spur | SummonVar(3m), HealVar(5m) | CreatureCmd.TriggerAnim, OstyCmd.Summon, CreatureCmd.Heal | UpgradeValueBy(2m) |
| Squash | DamageVar(10m, ValueProp.Move), PowerVar<VulnerablePower>(2m) | DamageCmd.Attack, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Squeeze | CalculationBaseVar(25m), ExtraDamageVar(5m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(5m), UpgradeValueBy(1m) |
| Stack | CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedBlockVar(ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| Stampede | DynamicVar("Power", 1m) | PowerCmd.Apply<StampedePower> |  |
| Stardust | DamageVar(5m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(2m) |
| Stoke |  | CreatureCmd.TriggerAnim, CardCmd.Exhaust, CardPileCmd.Draw |  |
| Stomp | DamageVar(12m, ValueProp.Move) | CreatureCmd.TriggerAnim, DamageCmd.Attack | UpgradeValueBy(3m) |
| StoneArmor | PowerVar<PlatingPower>(4m) | PowerCmd.Apply<PlatingPower> | UpgradeValueBy(2m) |
| Storm | PowerVar<StormPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<StormPower> | UpgradeValueBy(1m) |
| StormOfSteel |  | CardCmd.Discard, CardCmd.Upgrade |  |
| Strangle | DamageVar(8m, ValueProp.Move), PowerVar<StranglePower>(2m) | DamageCmd.Attack, PowerCmd.Apply<StranglePower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| Stratagem |  | PowerCmd.Apply<StratagemPower> |  |
| StrikeDefect | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| StrikeIronclad | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| StrikeNecrobinder | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| StrikeRegent | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| StrikeSilent | DamageVar(6m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Subroutine |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<SubroutinePower> |  |
| SuckerPunch | DamageVar(8m, ValueProp.Move), PowerVar<WeakPower>(1m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower> | UpgradeValueBy(2m), UpgradeValueBy(1m) |
| SummonForth | ForgeVar(8) | CreatureCmd.TriggerAnim, ForgeCmd.Forge, CardPileCmd.Add | UpgradeValueBy(3m) |
| Sunder | DamageVar(24m, ValueProp.Move), EnergyVar(3) | DamageCmd.Attack, PlayerCmd.GainEnergy | UpgradeValueBy(8m) |
| Supercritical | EnergyVar(4) | CreatureCmd.TriggerAnim, PlayerCmd.GainEnergy | UpgradeValueBy(2m) |
| Supermassive | CalculationBaseVar(5m), ExtraDamageVar(3m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(1m) |
| Suppress | DamageVar(11m, ValueProp.Move), PowerVar<WeakPower>(3m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower> | UpgradeValueBy(6m), UpgradeValueBy(2m) |
| Survivor | BlockVar(8m, ValueProp.Move) | CreatureCmd.GainBlock, CardSelectCmd.FromHandForDiscard, CardCmd.Discard | UpgradeValueBy(3m) |
| SweepingBeam | DamageVar(6m, ValueProp.Move), CardsVar(1) | CreatureCmd.TriggerAnim, DamageCmd.Attack, CardPileCmd.Draw | UpgradeValueBy(3m) |
| SweepingGaze | OstyDamageVar(10m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(5m) |
| SwordBoomerang | DamageVar(3m, ValueProp.Move), RepeatVar(3) | DamageCmd.Attack | UpgradeValueBy(1m) |
| SwordSage | PowerVar<SwordSagePower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<SwordSagePower> |  |
| Synchronize | CalculationBaseVar(0m), CalculationExtraVar(2m), CalculatedVar("CalculatedFocus") | CreatureCmd.TriggerAnim, PowerCmd.Apply<SynchronizePower> |  |
| Synthesis | DamageVar(12m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<FreePowerPower> | UpgradeValueBy(6m) |
| Tactician | EnergyVar(1) | PlayerCmd.GainEnergy | UpgradeValueBy(1m) |
| TagTeam | DamageVar(11m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<TagTeamPower> | UpgradeValueBy(4m) |
| Tank |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<TankPower> |  |
| Taunt | BlockVar(7m, ValueProp.Move), PowerVar<VulnerablePower>(1m) | CreatureCmd.TriggerAnim, CreatureCmd.GainBlock, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(1m) |
| TearAsunder | DamageVar(5m, ValueProp.Move), RepeatVar(1), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits") | DamageCmd.Attack | UpgradeValueBy(2m) |
| Tempest |  | CreatureCmd.TriggerAnim, OrbCmd.Channel<LightningOrb> |  |
| Terraforming | PowerVar<VigorPower>(6m) | PowerCmd.Apply<VigorPower> | UpgradeValueBy(2m) |
| TeslaCoil | DamageVar(3m, ValueProp.Move) | DamageCmd.Attack, OrbCmd.Passive | UpgradeValueBy(3m) |
| TheBomb | DynamicVar("Turns", 3m), DynamicVar("BombDamage", 40m) | PowerCmd.Apply<TheBombPower> | UpgradeValueBy(10m) |
| TheGambit | BlockVar(50m, ValueProp.Move) | CreatureCmd.GainBlock, PowerCmd.Apply<TheGambitPower> | UpgradeValueBy(25m) |
| TheHunt | DamageVar(10m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<TheHuntPower> | UpgradeValueBy(5m) |
| TheScythe | DamageVar(CurrentDamage, ValueProp.Move), IntVar("Increase", 3m) | DamageCmd.Attack | UpgradeValueBy(1m) |
| TheSealedThrone |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<TheSealedThronePower> | AddKeyword(Innate) |
| TheSmith | ForgeVar(30) | CreatureCmd.TriggerAnim, ForgeCmd.Forge | UpgradeValueBy(10m) |
| ThinkingAhead | CardsVar(2) | CardPileCmd.Draw, CardSelectCmd.FromHand, CardPileCmd.Add |  |
| Thrash | DamageVar(4m, ValueProp.Move) | DamageCmd.Attack, CardCmd.Exhaust | UpgradeValueBy(2m) |
| ThrummingHatchet | DamageVar(11m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Thunder | PowerVar<ThunderPower>(6m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ThunderPower> | UpgradeValueBy(2m) |
| Thunderclap | DamageVar(4m, ValueProp.Move), PowerVar<VulnerablePower>(1m) | DamageCmd.Attack, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(3m) |
| TimesUp | CalculationBaseVar(0m), ExtraDamageVar(1m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | AddKeyword(Retain) |
| ToolsOfTheTrade |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<ToolsOfTheTradePower> |  |
| ToricToughness | DynamicVar("Turns", 2m), BlockVar(5m, ValueProp.Move) | CreatureCmd.GainBlock, PowerCmd.Apply<ToricToughnessPower> | UpgradeValueBy(2m) |
| Toxic | DamageVar(5m, ValueProp.Unpowered \\| ValueProp.Move) |  |  |
| Tracking |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<TrackingPower> |  |
| Transfigure | EnergyVar(1) | CardSelectCmd.FromHand |  |
| TrashToTreasure |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<TrashToTreasurePower> | AddKeyword(Innate) |
| Tremble | PowerVar<VulnerablePower>(2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(1m) |
| TrueGrit | BlockVar(7m, ValueProp.Move) | CreatureCmd.GainBlock, CardSelectCmd.FromHand, CardCmd.Exhaust | UpgradeValueBy(2m) |
| Turbo | EnergyVar(2) | PlayerCmd.GainEnergy, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(1m) |
| TwinStrike | DamageVar(5m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(2m) |
| Tyranny |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<TyrannyPower> | AddKeyword(Innate) |
| UltimateDefend | BlockVar(11m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(4m) |
| UltimateStrike | DamageVar(14m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(6m) |
| Undeath | BlockVar(7m, ValueProp.Move) | CreatureCmd.GainBlock, CardCmd.PreviewCardPileAdd, CardPileCmd.AddGeneratedCardToCombat | UpgradeValueBy(2m) |
| Unleash | CalculationBaseVar(6m), ExtraDamageVar(1m), CalculatedDamageVar(ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(3m) |
| Unmovable |  | CreatureCmd.TriggerAnim, PowerCmd.Apply<UnmovablePower> |  |
| Unrelenting | DamageVar(12m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<FreeAttackPower> | UpgradeValueBy(6m) |
| Untouchable | BlockVar(9m, ValueProp.Move) | CreatureCmd.GainBlock | UpgradeValueBy(3m) |
| UpMySleeve | CardsVar(3) | CreatureCmd.TriggerAnim | UpgradeValueBy(1m) |
| Uppercut | DamageVar(13m, ValueProp.Move), DynamicVar("Power", 1m) | DamageCmd.Attack, PowerCmd.Apply<WeakPower>, PowerCmd.Apply<VulnerablePower> | UpgradeValueBy(1m) |
| Uproar | DamageVar(5m, ValueProp.Move) | DamageCmd.Attack, CardCmd.AutoPlay | UpgradeValueBy(2m) |
| Veilpiercer | DamageVar(10m, ValueProp.Move) | DamageCmd.Attack, PowerCmd.Apply<VeilpiercerPower> | UpgradeValueBy(3m) |
| Venerate | StarsVar(2) | CreatureCmd.TriggerAnim, PlayerCmd.GainStars | UpgradeValueBy(1m) |
| Vicious | CardsVar(1) | CreatureCmd.TriggerAnim, PowerCmd.Apply<ViciousPower> | UpgradeValueBy(1m) |
| Void | EnergyVar(1) |  |  |
| VoidForm | PowerVar<VoidFormPower>(2m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<VoidFormPower>, PlayerCmd.EndTurn | UpgradeValueBy(1m) |
| Volley | DamageVar(10m, ValueProp.Move) | DamageCmd.Attack | UpgradeValueBy(4m) |
| Voltaic | CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedChannels") | CreatureCmd.TriggerAnim, OrbCmd.Channel<LightningOrb> |  |
| WasteAway | PowerVar<WasteAwayPower>(1m) |  |  |
| WellLaidPlans | DynamicVar("RetainAmount", 1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<WellLaidPlansPower> | UpgradeValueBy(1m) |
| Whirlwind | DamageVar(5m, ValueProp.Move) | SfxCmd.Play, DamageCmd.Attack | UpgradeValueBy(3m) |
| Whistle | DamageVar(33m, ValueProp.Move) | DamageCmd.Attack, CreatureCmd.Stun | UpgradeValueBy(11m) |
| WhiteNoise |  | CreatureCmd.TriggerAnim, CardPileCmd.AddGeneratedCardToCombat |  |
| Wish |  | CardSelectCmd.FromSimpleGrid, CardPileCmd.Add | AddKeyword(Retain) |
| Wisp | EnergyVar(1) | PlayerCmd.GainEnergy | AddKeyword(Retain) |
| Wound |  |  |  |
| WraithForm | PowerVar<IntangiblePower>(2m), PowerVar<WraithFormPower>(1m) | CreatureCmd.TriggerAnim, PowerCmd.Apply<IntangiblePower>, PowerCmd.Apply<WraithFormPower> | UpgradeValueBy(1m) |
| Writhe |  |  |  |
| WroughtInWar | DamageVar(7m, ValueProp.Move), ForgeVar(5) | DamageCmd.Attack, ForgeCmd.Forge | UpgradeValueBy(2m) |
| Zap |  | CreatureCmd.TriggerAnim, OrbCmd.Channel<LightningOrb> |  |
