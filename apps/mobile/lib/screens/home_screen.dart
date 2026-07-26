import 'package:flutter/material.dart';
import 'package:zarma_mobile/navigation/app_routes.dart';
import 'package:zarma_mobile/theme/brand.dart';
import 'package:zarma_mobile/widgets/brand_app_bar.dart';
import 'package:zarma_mobile/widgets/brand_footer.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('home-screen'),
      appBar:
          const BrandAppBar(title: 'ZarmaIA', automaticallyImplyLeading: false),
      bottomNavigationBar: const BrandFooter(),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (BuildContext context, BoxConstraints constraints) {
            final double buttonDiameter =
                constraints.biggest.shortestSide.clamp(220, 260).toDouble();
            return Stack(
              fit: StackFit.expand,
              alignment: Alignment.center,
              children: <Widget>[
                Positioned(
                  top: 16,
                  left: 16,
                  right: 16,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(16),
                    child: Image.asset(
                      'brand-source/logo.png',
                      key: const Key('home-brand-logo'),
                      fit: BoxFit.fitWidth,
                    ),
                  ),
                ),
                Center(
                  child: Semantics(
                    button: true,
                    label: 'Démarrer un enregistrement audio',
                    child: ExcludeSemantics(
                      child: SizedBox(
                        width: buttonDiameter,
                        height: buttonDiameter,
                        child: FilledButton(
                          key: const Key('start-recording-button'),
                          onPressed: () => Navigator.of(context)
                              .pushNamed(AppRoutes.recording),
                          style: FilledButton.styleFrom(
                            shape: const CircleBorder(),
                            backgroundColor: BrandColors.blue,
                            elevation: 6,
                          ),
                          child: const Column(
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Icon(Icons.mic, size: 96, color: Colors.white),
                              SizedBox(height: 8),
                              Text(
                                'Enregistrer',
                                style: TextStyle(
                                  fontSize: 24,
                                  fontWeight: FontWeight.w800,
                                  color: Colors.white,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
